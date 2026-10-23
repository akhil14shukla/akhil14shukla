#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["psycopg[binary]>=3.1", "PyYAML>=6.0"]
# ///
"""Black-box scenario runner: known database in, API calls, known database out.

Each scenario is a YAML file that states the whole truth of one business case:

    given   the exact rows in Postgres and how faked external systems behave
    when    the HTTP calls made against the running application
    then    the responses, the rows that must exist afterwards, the tables that
            must not have changed, and the calls the external systems must have received

The runner is language-agnostic: the application under test runs as its own
process or container, pointed at the e2e database and at a WireMock server
standing in for every external HTTP system it calls (ERP, payment provider, ...).
Before every scenario the runner resets both, so each
scenario starts from a state you wrote down and therefore knows the answer to.

    uv run scenario_runner.py --config e2e/e2e.config.yaml prepare
    uv run scenario_runner.py --config e2e/e2e.config.yaml run
    uv run scenario_runner.py --config e2e/e2e.config.yaml run --filter ORD-PAY --junit out/junit.xml
    uv run scenario_runner.py --config e2e/e2e.config.yaml run --capture out/actual   # draft expectations

Exit codes: 0 all passed, 1 a scenario failed, 2 configuration or environment error.
"""

from __future__ import annotations

import argparse
import datetime as dt
import decimal
import fnmatch
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape

import psycopg
import yaml
from psycopg import sql
from psycopg.types.json import Jsonb

MATCHER = re.compile(r"^\{\{(any|not_null|uuid|iso_datetime|regex:.*|contains:.*|gt:.*|lt:.*)\}\}$", re.S)
VAR = re.compile(r"\{\{\s*([A-Za-z_][\w.]*)\s*\}\}")
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


class ConfigError(Exception):
    """The harness is misconfigured; no scenario result can be trusted."""


class ScenarioFailure(Exception):
    """An expectation in a scenario did not hold."""


# --------------------------------------------------------------------------- config


@dataclass(frozen=True, slots=True)
class Config:
    root: Path
    raw: dict[str, Any]

    @property
    def db(self) -> dict[str, Any]:
        return self.raw["database"]

    @property
    def app(self) -> dict[str, Any]:
        return self.raw["app"]

    @property
    def mock(self) -> dict[str, Any] | None:
        return self.raw.get("mock")

    @property
    def snapshot(self) -> dict[str, Any]:
        return self.raw.get("snapshot") or {}

    def path(self, p: str) -> Path:
        return (self.root / p).resolve()


def load_config(path: Path) -> Config:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    for key in ("database", "app", "scenarios"):
        if key not in raw:
            raise ConfigError(f"{path}: missing top-level key {key!r}")
    raw["database"] = expand_env(raw["database"])
    raw["app"] = expand_env(raw["app"])
    if raw.get("mock"):
        raw["mock"] = expand_env(raw["mock"])
    if raw["database"].get("reset", "truncate") not in ("truncate", "template"):
        raise ConfigError("database.reset must be 'truncate' or 'template'")
    return Config(root=path.parent.resolve(), raw=raw)


def expand_env(obj: Any) -> Any:
    """Expand ${VAR} and ${VAR:-default} so CI can override DSNs and URLs."""
    if isinstance(obj, str):
        return re.sub(
            r"\$\{(\w+)(?::-([^}]*))?\}",
            lambda m: os.environ.get(m.group(1), m.group(2) or ""),
            obj,
        )
    if isinstance(obj, dict):
        return {k: expand_env(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [expand_env(v) for v in obj]
    return obj


# --------------------------------------------------------------------------- values


def canonical(value: Any) -> Any:
    """Turn DB and YAML values into comparable JSON-ish values."""
    if isinstance(value, decimal.Decimal):
        return value
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, (dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (bytes, memoryview)):
        return bytes(value).hex()
    if isinstance(value, dict):
        return {k: canonical(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [canonical(v) for v in value]
    return value


def as_decimal(value: Any) -> decimal.Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, decimal.Decimal)):
        return decimal.Decimal(str(value))
    if isinstance(value, str) and re.fullmatch(r"-?\d+(\.\d+)?", value.strip()):
        return decimal.Decimal(value.strip())
    return None


def as_instant(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", value):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def match_value(expected: Any, actual: Any, where: str) -> list[str]:
    """Return mismatch descriptions; empty means `actual` satisfies `expected`.

    Dicts match as subsets (unlisted keys are ignored), lists match element-wise
    with equal length, numbers compare as decimals, timestamps as instants, and
    `{{matcher}}` strings express "any", "not_null", "regex:...", and so on.
    """
    expected, actual = canonical(expected), canonical(actual)
    if isinstance(expected, str) and (m := MATCHER.match(expected)):
        return check_matcher(m.group(1), actual, where)
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{where}: expected an object, got {actual!r}"]
        problems: list[str] = []
        for key, exp in expected.items():
            if key not in actual:
                problems.append(f"{where}.{key}: missing (expected {exp!r})")
            else:
                problems += match_value(exp, actual[key], f"{where}.{key}")
        return problems
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return [f"{where}: expected a list, got {actual!r}"]
        if len(expected) != len(actual):
            return [f"{where}: expected {len(expected)} items, got {len(actual)}: {actual!r}"]
        problems = []
        for i, (exp, act) in enumerate(zip(expected, actual, strict=True)):
            problems += match_value(exp, act, f"{where}[{i}]")
        return problems
    if expected is None or actual is None or isinstance(expected, bool) or isinstance(actual, bool):
        return [] if expected == actual else [f"{where}: expected {expected!r}, got {actual!r}"]
    exp_num, act_num = as_decimal(expected), as_decimal(actual)
    if exp_num is not None and act_num is not None:
        return [] if exp_num == act_num else [f"{where}: expected {expected}, got {actual}"]
    exp_t, act_t = as_instant(expected), as_instant(actual)
    if exp_t is not None and act_t is not None:
        return [] if exp_t == act_t else [f"{where}: expected {expected}, got {actual}"]
    return [] if str(expected) == str(actual) else [f"{where}: expected {expected!r}, got {actual!r}"]


def check_matcher(spec: str, actual: Any, where: str) -> list[str]:
    ok: bool
    if spec == "any":
        ok = True
    elif spec == "not_null":
        ok = actual is not None
    elif spec == "uuid":
        ok = isinstance(actual, str) and bool(UUID_RE.match(actual))
    elif spec == "iso_datetime":
        ok = as_instant(actual) is not None
    elif spec.startswith("regex:"):
        ok = actual is not None and re.search(spec[6:], str(actual)) is not None
    elif spec.startswith("contains:"):
        ok = actual is not None and spec[9:] in str(actual)
    else:  # gt: / lt:
        bound, value = as_decimal(spec[3:]), as_decimal(actual)
        ok = bound is not None and value is not None and (value > bound if spec[:2] == "gt" else value < bound)
    return [] if ok else [f"{where}: {actual!r} does not satisfy {{{{{spec}}}}}"]


def render(obj: Any, variables: dict[str, Any]) -> Any:
    """Substitute {{name}} with saved variables, leaving matchers for match_value.

    A string that is exactly one variable becomes that variable's raw value, so
    an integer id stays an integer in a JSON body.
    """
    if isinstance(obj, str):
        whole = VAR.fullmatch(obj.strip())
        if whole and whole.group(1) in variables:
            return variables[whole.group(1)]
        return VAR.sub(lambda m: str(variables[m.group(1)]) if m.group(1) in variables else m.group(0), obj)
    if isinstance(obj, dict):
        return {k: render(v, variables) for k, v in obj.items()}
    if isinstance(obj, list):
        return [render(v, variables) for v in obj]
    return obj


def json_path(doc: Any, path: str) -> Any:
    """Minimal JSONPath: $.a.b[0].c — enough to save ids from responses."""
    if not path.startswith("$"):
        raise ConfigError(f"JSON path must start with '$': {path!r}")
    current = doc
    for name, index in re.findall(r"\.([A-Za-z_@][\w@-]*)|\[(\d+)\]", path[1:]):
        try:
            current = current[name] if name else current[int(index)]
        except (KeyError, IndexError, TypeError) as exc:
            raise ScenarioFailure(f"path {path!r} not found in {json.dumps(doc)[:500]}") from exc
    return current


# --------------------------------------------------------------------------- http


@dataclass(slots=True)
class Response:
    status: int
    body: Any
    text: str


def http(method: str, url: str, body: Any = None, headers: dict[str, str] | None = None, timeout: float = 30) -> Response:
    data = None
    hdrs = {"Accept": "application/json", **(headers or {})}
    if body is not None:
        data = body.encode() if isinstance(body, str) else json.dumps(body, default=str).encode()
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - test harness, URLs come from config
            status, raw = resp.status, resp.read()
    except urllib.error.HTTPError as err:
        status, raw = err.code, err.read()
    text = raw.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(text) if text.strip() else None
    except json.JSONDecodeError:
        parsed = text
    return Response(status, parsed, text)


def wait_until_ready(cfg: Config) -> None:
    ready = cfg.app.get("ready") or {}
    url = cfg.app["base_url"].rstrip("/") + ready.get("path", "/health")
    deadline = time.monotonic() + float(ready.get("timeout_s", 60))
    last = ""
    while time.monotonic() < deadline:
        try:
            if http("GET", url, timeout=5).status < 300:
                return
        except OSError as exc:
            last = str(exc)
        time.sleep(0.5)
    raise ConfigError(f"app not ready at {url} ({last})")


# --------------------------------------------------------------------------- database


def connect(dsn: str, autocommit: bool = True) -> psycopg.Connection:
    conn = psycopg.connect(dsn, autocommit=autocommit)
    conn.execute("SET TIME ZONE 'UTC'")
    return conn


def db_name(dsn: str) -> str:
    return urllib.parse.urlparse(dsn).path.lstrip("/")


def with_db(dsn: str, name: str) -> str:
    parts = urllib.parse.urlparse(dsn)
    return urllib.parse.urlunparse(parts._replace(path="/" + name))


def recreate_database(admin_dsn: str, name: str, template: str | None = None) -> None:
    with connect(admin_dsn) as conn:
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))
        if template:
            conn.execute(sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(sql.Identifier(name), sql.Identifier(template)))
        else:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))


def run_sql_file(conn: psycopg.Connection, path: Path) -> None:
    if not path.exists():
        raise ConfigError(f"SQL file not found: {path}")
    conn.execute(path.read_text(encoding="utf-8"))


def prepare(cfg: Config) -> None:
    """Create the database the scenarios clone from, migrated and base-seeded.

    truncate mode: the app's own database is built once; resets truncate it.
    template mode: a template database is built once; resets clone it.
    """
    admin, target = cfg.db["admin_dsn"], cfg.db["dsn"]
    build_name = cfg.db["template"] if cfg.db.get("reset") == "template" else db_name(target)
    build_dsn = with_db(target, build_name)
    if cfg.db.get("reset") == "template":
        with connect(admin) as conn:
            conn.execute(sql.SQL("UPDATE pg_database SET datistemplate = false WHERE datname = {}").format(sql.Literal(build_name)))
    recreate_database(admin, build_name)

    if command := cfg.db.get("migrate_command"):
        env = {**os.environ, cfg.db.get("url_env", "DATABASE_URL"): build_dsn}
        print(f"migrate: {command}")
        done = subprocess.run(command, shell=True, cwd=cfg.root, env=env, check=False)  # noqa: S602 - command is the repo's own
        if done.returncode != 0:
            raise ConfigError(f"migrate_command exited {done.returncode}")
    with connect(build_dsn) as conn:
        for f in cfg.db.get("schema_files", []):
            run_sql_file(conn, cfg.path(f))
        if cfg.db.get("reset") == "template":
            for f in cfg.db.get("base_seed", []):
                run_sql_file(conn, cfg.path(f))
    if cfg.db.get("reset") == "template":
        with connect(admin) as conn:
            conn.execute(sql.SQL("ALTER DATABASE {} WITH IS_TEMPLATE true ALLOW_CONNECTIONS false").format(sql.Identifier(build_name)))
    print(f"prepared database {build_name!r} ({cfg.db.get('reset', 'truncate')} mode)")


def reset_database(cfg: Config) -> None:
    if cfg.db.get("reset") == "template":
        recreate_database(cfg.db["admin_dsn"], db_name(cfg.db["dsn"]), cfg.db["template"])
        return
    schemas = cfg.db.get("schemas", ["public"])
    keep = set(cfg.db.get("keep_tables", []))
    with connect(cfg.db["dsn"]) as conn:
        rows = conn.execute(
            "SELECT schemaname, tablename FROM pg_tables WHERE schemaname = ANY(%s) ORDER BY 1, 2", (schemas,)
        ).fetchall()
        tables = [sql.Identifier(s, t) for s, t in rows if t not in keep and f"{s}.{t}" not in keep]
        if tables:
            conn.execute(sql.SQL("TRUNCATE {} RESTART IDENTITY CASCADE").format(sql.SQL(", ").join(tables)))
        for seq_schema, seq in conn.execute(
            "SELECT sequence_schema, sequence_name FROM information_schema.sequences WHERE sequence_schema = ANY(%s)",
            (schemas,),
        ).fetchall():
            conn.execute(sql.SQL("ALTER SEQUENCE {} RESTART").format(sql.Identifier(seq_schema, seq)))
        for f in cfg.db.get("base_seed", []):
            run_sql_file(conn, cfg.path(f))


def insert_rows(conn: psycopg.Connection, table: str, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        cols = list(row)
        values = [Jsonb(v) if isinstance(v, (dict, list)) else v for v in row.values()]
        conn.execute(
            sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                sql.Identifier(*table.split(".")),
                sql.SQL(", ").join(map(sql.Identifier, cols)),
                sql.SQL(", ").join(sql.Placeholder() * len(cols)),
            ),
            values,
        )


def fetch_rows(conn: psycopg.Connection, table: str, where: str | None, order_by: str | None) -> list[dict[str, Any]]:
    query = sql.SQL("SELECT * FROM {}").format(sql.Identifier(*table.split(".")))
    if where:
        query += sql.SQL(" WHERE ") + sql.SQL(where)  # type: ignore[arg-type] - test-authored SQL
    if order_by:
        query += sql.SQL(" ORDER BY ") + sql.SQL(order_by)  # type: ignore[arg-type]
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        return [canonical(r) for r in cur.execute(query).fetchall()]


def snapshot_tables(cfg: Config, conn: psycopg.Connection, tables: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Full contents of `tables`, minus volatile columns, in a stable order."""
    ignore = set(cfg.snapshot.get("ignore_columns", []))
    table_cfg = cfg.snapshot.get("tables") or {}
    out: dict[str, list[dict[str, Any]]] = {}
    for t in tables:
        tcfg = table_cfg.get(t) or {}
        drop = ignore | set(tcfg.get("ignore_columns", []))
        rows = [{k: v for k, v in r.items() if k not in drop} for r in fetch_rows(conn, t, None, None)]
        key = tcfg.get("key")
        out[t] = sorted(rows, key=lambda r: json.dumps([r.get(k) for k in key] if key else r, sort_keys=True, default=str))
    return out


def assign_rows(expected: list[dict[str, Any]], actual: list[dict[str, Any]]) -> list[int | None]:
    """One-to-one assignment of expected rows to matching actual rows (bipartite matching)."""
    candidates = [[j for j, a in enumerate(actual) if not match_value(e, a, "")] for e in expected]
    owner: dict[int, int] = {}

    def try_assign(i: int, seen: set[int]) -> bool:
        for j in candidates[i]:
            if j in seen:
                continue
            seen.add(j)
            if j not in owner or try_assign(owner[j], seen):
                owner[j] = i
                return True
        return False

    for i in range(len(expected)):
        try_assign(i, set())
    result: list[int | None] = [None] * len(expected)
    for j, i in owner.items():
        result[i] = j
    return result


def check_table(conn: psycopg.Connection, table: str, spec: dict[str, Any]) -> list[str]:
    mode = spec.get("mode", "exact")
    actual = fetch_rows(conn, table, spec.get("where"), spec.get("order_by"))
    expected = spec.get("rows", [])
    label = f"db.{table}" + (f" where {spec['where']}" if spec.get("where") else "")
    if "count" in spec and len(actual) != spec["count"]:
        return [f"{label}: expected {spec['count']} rows, got {len(actual)}: {actual}"]
    if "rows" not in spec:
        return []
    if mode == "absent":
        hits = [a for a in actual if any(not match_value(e, a, "") for e in expected)]
        return [f"{label}: rows that must be absent exist: {hits}"] if hits else []
    if spec.get("order_by") and mode == "exact":
        if len(actual) != len(expected):
            return [f"{label}: expected {len(expected)} rows, got {len(actual)}: {actual}"]
        problems: list[str] = []
        for i, (e, a) in enumerate(zip(expected, actual, strict=True)):
            problems += match_value(e, a, f"{label}[{i}]")
        return problems
    assignment = assign_rows(expected, actual)
    problems = []
    for e, j in zip(expected, assignment, strict=True):
        if j is None:
            closest = min(actual, key=lambda a: len(match_value(e, a, "")), default=None)
            detail = "; ".join(match_value(e, closest, "closest row")) if closest else "table is empty"
            problems.append(f"{label}: no row matches {e} ({detail})")
    if mode == "exact" and len(actual) != len(expected):
        extra = [a for j, a in enumerate(actual) if j not in assignment]
        problems.append(f"{label}: expected exactly {len(expected)} rows, got {len(actual)}; unexpected: {extra}")
    return problems


def diff_snapshots(before: dict[str, list[dict[str, Any]]], after: dict[str, list[dict[str, Any]]]) -> list[str]:
    problems = []
    for table, rows in before.items():
        gone = [r for r in rows if r not in after[table]]
        new = [r for r in after[table] if r not in rows]
        if gone or new:
            problems.append(f"db.{table} changed but must not: removed/changed-from {gone} added/changed-to {new}")
    return problems


# --------------------------------------------------------------------------- external http mock


class HttpMock:
    """WireMock admin API for the faked external systems: reset, stub, read the request journal."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.url = cfg.mock["admin_url"].rstrip("/") if cfg.mock else None

    def _admin(self, method: str, path: str, body: Any = None) -> Response:
        assert self.url is not None
        resp = http(method, f"{self.url}/__admin{path}", body)
        if resp.status >= 300:
            raise ConfigError(f"WireMock {method} {path} -> {resp.status}: {resp.text[:300]}")
        return resp

    def reset(self) -> None:
        if self.url:
            self._admin("POST", "/reset")  # mappings back to files on disk, journal cleared
            self._admin("POST", "/scenarios/reset")

    def stub(self, mapping: dict[str, Any]) -> None:
        if not self.url:
            raise ConfigError("scenario declares mock_stubs but config has no mock section")
        self._admin("POST", "/mappings", mapping)

    def requests(self) -> list[dict[str, Any]]:
        if not self.url:
            return []
        entries = self._admin("GET", "/requests").body.get("requests", [])
        return list(reversed(entries))  # journal is newest-first; scenarios read oldest-first

    def unmatched(self) -> list[dict[str, Any]]:
        return self._admin("GET", "/requests/unmatched").body.get("requests", []) if self.url else []


def load_stubs(items: list[Any], base: Path, variables: dict[str, Any]) -> list[dict[str, Any]]:
    stubs: list[dict[str, Any]] = []
    for item in items or []:
        if isinstance(item, dict) and "file" in item:
            doc = json.loads((base / item["file"]).read_text(encoding="utf-8"))
            stubs += doc.get("mappings", [doc])
        else:
            stubs.append(item.get("inline", item) if isinstance(item, dict) else item)
    return [render(s, variables) for s in stubs]


def check_mock_calls(journal: list[dict[str, Any]], expectations: list[dict[str, Any]]) -> list[str]:
    problems = []
    for exp in expectations:
        hits = []
        for entry in journal:
            req = entry["request"]
            path = urllib.parse.urlparse(req["url"]).path
            if exp.get("method") and req["method"].upper() != exp["method"].upper():
                continue
            if exp.get("url_path") and path != exp["url_path"]:
                continue
            if exp.get("url_path_pattern") and not re.search(exp["url_path_pattern"], path):
                continue
            if exp.get("body_contains") and exp["body_contains"] not in req.get("body", ""):
                continue
            if "json" in exp:
                try:
                    body = json.loads(req.get("body") or "null")
                except json.JSONDecodeError:
                    continue
                if match_value(exp["json"], body, "body"):
                    continue
            hits.append(req)
        label = f"mock {exp.get('method', '*')} {exp.get('url_path') or exp.get('url_path_pattern', '*')}"
        if "count" in exp and len(hits) != exp["count"]:
            seen = [f"{e['request']['method']} {e['request']['url']} {e['request'].get('body', '')[:200]}" for e in journal]
            problems.append(f"{label}: expected {exp['count']} matching calls, got {len(hits)}. Journal: {seen}")
        elif "count" not in exp and not hits:
            problems.append(f"{label}: expected at least one matching call, got none")
    return problems


def check_mock_sequence(journal: list[dict[str, Any]], sequence: list[str]) -> list[str]:
    """`sequence` is a list of 'METHOD /path' that must appear in this relative order."""
    calls = [f"{e['request']['method']} {urllib.parse.urlparse(e['request']['url']).path}" for e in journal]
    pos = 0
    for call in calls:
        if pos < len(sequence) and fnmatch.fnmatch(call, sequence[pos]):
            pos += 1
    return [] if pos == len(sequence) else [f"mock call order: expected subsequence {sequence}, got {calls}"]


# --------------------------------------------------------------------------- scenarios


@dataclass(slots=True)
class Result:
    scenario_id: str
    title: str
    path: Path
    seconds: float = 0.0
    failures: list[str] = field(default_factory=list)
    error: str | None = None
    skipped: str | None = None

    @property
    def passed(self) -> bool:
        return not self.failures and self.error is None and self.skipped is None


def discover(cfg: Config) -> list[tuple[Path, dict[str, Any]]]:
    found: list[tuple[Path, dict[str, Any]]] = []
    for pattern in cfg.raw["scenarios"]:
        for p in sorted(glob.glob(str(cfg.root / pattern), recursive=True)):
            doc = yaml.safe_load(Path(p).read_text(encoding="utf-8"))
            if not isinstance(doc, dict) or "id" not in doc:
                raise ConfigError(f"{p}: a scenario needs at least an 'id'")
            found.append((Path(p), doc))
    ids = [d["id"] for _, d in found]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ConfigError(f"duplicate scenario ids: {sorted(dupes)}")
    return found


def selected(doc: dict[str, Any], filters: list[str], shard: tuple[int, int] | None) -> bool:
    if filters:
        haystack = [doc["id"], *doc.get("tags", [])]
        if not any(f in h for f in filters for h in haystack):
            return False
    if shard:
        index, total = shard
        bucket = int(hashlib.sha1(doc["id"].encode()).hexdigest(), 16) % total
        return bucket == index - 1
    return True


def run_scenario(cfg: Config, mock: HttpMock, path: Path, doc: dict[str, Any], capture: Path | None) -> Result:
    result = Result(doc["id"], doc.get("title", ""), path)
    started = time.monotonic()
    base = path.parent
    variables: dict[str, Any] = {"scenario_id": doc["id"]}
    if doc.get("clock"):
        variables["clock"] = canonical(doc["clock"])
    try:
        reset_database(cfg)
        mock.reset()
        given = doc.get("given") or {}
        with connect(cfg.db["dsn"]) as conn:
            for f in given.get("sql", []):
                run_sql_file(conn, (base / f).resolve())
            for table, rows in (given.get("rows") or {}).items():
                insert_rows(conn, table, render(rows, variables))
        for stub in load_stubs(given.get("mock_stubs", []), base, variables):
            mock.stub(stub)
        if variables.get("clock") and (clock := cfg.app.get("clock")):
            resp = app_call(cfg, render(clock, variables))
            if resp.status >= 300:
                raise ConfigError(f"setting clock failed: {resp.status} {resp.text[:300]}")

        then = doc.get("then") or {}
        with connect(cfg.db["dsn"]) as conn:
            before = snapshot_tables(cfg, conn, then.get("db_unchanged", []))

        for i, step in enumerate(doc.get("when") or []):
            run_step(cfg, mock, step, i, base, variables, result)
            if result.failures and not step.get("continue_on_failure"):
                break

        if not result.failures:
            with connect(cfg.db["dsn"]) as conn:
                for table, spec in (render(then.get("db") or {}, variables)).items():
                    result.failures += check_table(conn, table, spec)
                result.failures += diff_snapshots(before, snapshot_tables(cfg, conn, list(before)))
            journal = mock.requests()
            result.failures += check_mock_calls(journal, render(then.get("mock_requests") or [], variables))
            if then.get("mock_sequence"):
                result.failures += check_mock_sequence(journal, then["mock_sequence"])
            if then.get("mock_unmatched", "none") == "none" and (unmatched := mock.unmatched()):
                calls = [f"{u['method']} {u['url']}" for u in unmatched]
                result.failures.append(f"app called external endpoints no stub covers: {calls}")
        if capture:
            write_capture(cfg, capture, doc["id"], mock)
    except ScenarioFailure as exc:
        result.failures.append(str(exc))
    except (ConfigError, psycopg.Error, OSError, KeyError, ValueError) as exc:
        result.error = f"{type(exc).__name__}: {exc}"
    result.seconds = time.monotonic() - started
    return result


def app_call(cfg: Config, spec: dict[str, Any]) -> Response:
    url = cfg.app["base_url"].rstrip("/") + spec["path"]
    if spec.get("query"):
        url += "?" + urllib.parse.urlencode(spec["query"])
    headers = {**(cfg.app.get("headers") or {}), **(spec.get("headers") or {})}
    body = spec.get("json", spec.get("body"))
    return http(spec.get("method", "GET"), url, body, headers, float(spec.get("timeout_s", 30)))


def run_step(
    cfg: Config, mock: HttpMock, step: dict[str, Any], i: int, base: Path, variables: dict[str, Any], result: Result
) -> None:
    name = step.get("name", f"step {i + 1}")
    step = {k: v for k, v in step.items() if k != "name"}
    if "request" in step:
        resp = app_call(cfg, render(step["request"], variables))
        expect = render(step.get("expect") or {}, variables)
        if "status" in expect and resp.status != expect["status"]:
            result.failures.append(f"{name}: expected HTTP {expect['status']}, got {resp.status}: {resp.text[:800]}")
            return
        if "json" in expect:
            result.failures += [f"{name}: {p}" for p in match_value(expect["json"], resp.body, "response")]
        if "body_contains" in expect and expect["body_contains"] not in resp.text:
            result.failures.append(f"{name}: response does not contain {expect['body_contains']!r}: {resp.text[:500]}")
        for var, path in (step.get("save") or {}).items():
            variables[var] = json_path(resp.body, path)
    elif "wait_for" in step:
        spec = render(step["wait_for"], variables)
        deadline = time.monotonic() + float(spec.get("timeout_s", 15))
        last: Any = None
        while True:
            with connect(cfg.db["dsn"]) as conn:
                row = conn.execute(spec["sql"]).fetchone()
            last = canonical(row[0]) if row else None
            if not match_value(spec["equals"], last, "value"):
                return
            if time.monotonic() > deadline:
                result.failures.append(f"{name}: timed out waiting for {spec['sql']!r} == {spec['equals']!r}; last {last!r}")
                return
            time.sleep(float(spec.get("interval_s", 0.25)))
    elif "sql" in step:
        with connect(cfg.db["dsn"]) as conn:
            conn.execute(render(step["sql"], variables))
    elif "mock_stubs" in step:
        for stub in load_stubs(step["mock_stubs"], base, variables):
            mock.stub(stub)
    elif "set" in step:
        variables.update(render(step["set"], variables))
    else:
        raise ConfigError(f"{name}: unknown step type {sorted(step)}")


def write_capture(cfg: Config, out: Path, scenario_id: str, mock: HttpMock) -> None:
    """Dump post-run state as a draft `then` block. A human must review it before committing."""
    tables = list((cfg.snapshot.get("tables") or {}).keys())
    with connect(cfg.db["dsn"]) as conn:
        state = snapshot_tables(cfg, conn, tables)
    calls = [
        {"method": e["request"]["method"], "url_path": urllib.parse.urlparse(e["request"]["url"]).path, "body": e["request"].get("body")}
        for e in mock.requests()
    ]
    out.mkdir(parents=True, exist_ok=True)
    doc = {"db": {t: {"mode": "exact", "rows": rows} for t, rows in state.items()}, "mock_calls_observed": calls}
    (out / f"{scenario_id}.actual.yaml").write_text(
        yaml.safe_dump(json.loads(json.dumps(doc, default=str)), sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


def write_junit(results: list[Result], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    failures = sum(1 for r in results if r.failures)
    errors = sum(1 for r in results if r.error)
    skips = sum(1 for r in results if r.skipped)
    cases = []
    for r in results:
        body = ""
        if r.skipped:
            body = f'<skipped message="{xml_escape(r.skipped[:200], {chr(34): "&quot;"})}"/>'
        elif r.error:
            body = f'<error message="{xml_escape(r.error[:200], {chr(34): "&quot;"})}">{xml_escape(r.error)}</error>'
        elif r.failures:
            text = "\n".join(r.failures)
            body = f'<failure message="{xml_escape(r.failures[0][:200], {chr(34): "&quot;"})}">{xml_escape(text)}</failure>'
        name = xml_escape(f"{r.scenario_id} {r.title}".strip(), {chr(34): "&quot;"})
        cases.append(f'  <testcase classname="e2e.{xml_escape(r.path.stem)}" name="{name}" time="{r.seconds:.3f}">{body}</testcase>')
    path.write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n<testsuite name="scenario-e2e" tests="{len(results)}" '
        f'failures="{failures}" errors="{errors}" skipped="{skips}">\n' + "\n".join(cases) + "\n</testsuite>\n",
        encoding="utf-8",
    )


def run_all(cfg: Config, args: argparse.Namespace) -> int:
    shard = None
    if args.shard:
        index, total = (int(x) for x in args.shard.split("/"))
        shard = (index, total)
    chosen = [(p, d) for p, d in discover(cfg) if selected(d, args.filter or [], shard)]
    scenarios = [(p, d) for p, d in chosen if not d.get("skip")]
    # Skipped scenarios are reported every run, so a quarantine is never silent.
    skipped = [Result(d["id"], d.get("title", ""), p, skipped=str(d["skip"])) for p, d in chosen if d.get("skip")]
    for r in skipped:
        print(f"[SKIP] {r.scenario_id} {r.title} — {r.skipped}")
    if not scenarios:
        print("no scenarios selected", file=sys.stderr)
        return 2
    wait_until_ready(cfg)
    mock = HttpMock(cfg)
    results: list[Result] = []
    for path, doc in scenarios:
        r = run_scenario(cfg, mock, path, doc, Path(args.capture) if args.capture else None)
        results.append(r)
        mark = "PASS" if r.passed else ("ERROR" if r.error else "FAIL")
        print(f"[{mark}] {r.scenario_id} {r.title} ({r.seconds:.2f}s)")
        for line in ([r.error] if r.error else r.failures):
            print(f"       - {line}")
        if args.fail_fast and not r.passed:
            break
    if args.junit:
        write_junit(results + skipped, Path(args.junit))
    passed = sum(r.passed for r in results)
    print(f"\n{passed}/{len(results)} scenarios passed" + (f", {len(skipped)} skipped" if skipped else ""))
    if any(r.error for r in results):
        return 2 if passed == 0 else 1
    return 0 if passed == len(results) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", required=True, type=Path, help="Path to e2e.config.yaml")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare", help="Create and migrate the e2e (or template) database")
    run = sub.add_parser("run", help="Run scenarios against the running app")
    run.add_argument("--filter", action="append", help="Substring of a scenario id or tag; repeatable")
    run.add_argument("--shard", help="i/n — run only shard i of n (1-based), stable by scenario id")
    run.add_argument("--junit", help="Write a JUnit XML report here")
    run.add_argument("--capture", help="Directory to write each scenario's actual end state, for drafting expectations")
    run.add_argument("--fail-fast", action="store_true")
    sub.add_parser("list", help="List scenarios with their tags")
    args = parser.parse_args(argv)

    try:
        cfg = load_config(args.config)
        if args.command == "prepare":
            prepare(cfg)
            return 0
        if args.command == "list":
            for path, doc in discover(cfg):
                print(f"{doc['id']:<24} {','.join(doc.get('tags', [])):<40} {path.relative_to(cfg.root)}")
            return 0
        return run_all(cfg, args)
    except (ConfigError, psycopg.Error, yaml.YAMLError) as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
