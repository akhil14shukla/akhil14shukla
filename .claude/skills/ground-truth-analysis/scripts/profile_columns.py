#!/usr/bin/env python3
"""Profile every column in a file: what it is, and what it is good for.

Most reconciliations compare two or three numeric columns and ignore the twenty
others, which is where the explanation usually lives — the batch id that dates
the bad load, the status that silently defines scope, the currency that makes a
total meaningless. This reads the file and says, for every column, what role it
plays, how it is distributed, which columns identify a row, which determine
which, and which are computed from others.

    python profile_columns.py --file export.csv
    python profile_columns.py --file export.xlsx --sheet Orders --key order_id
    python profile_columns.py --file jan.csv --file feb.csv   # same names, same meaning?

Stdlib only, via tabular.py. Roles are inferred from names and statistics, so
treat them as a starting point to confirm, not as a data dictionary.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from tabular import Row, load, money, to_decimal

SAMPLE_LIMIT = 20000  # rows used for the pairwise checks

METADATA_RE = re.compile(
    r"(^|_)(batch|load|loaded|ingest|ingested|etl|run|job|source|src|file|filename|version|"
    r"snapshot|vintage|valid_from|valid_to|effective_from|effective_to|is_deleted|deleted|"
    r"created_by|updated_by|modified_by|row_hash|checksum|_ts|_at)($|_)", re.I)
IDENTITY_RE = re.compile(r"(^|_)(id|key|no|num|number|code|ref|reference|uuid|guid|sku|account)($|_)", re.I)
MEASURE_RE = re.compile(
    r"(^|_)(amount|amt|value|val|total|sum|qty|quantity|units|count|price|cost|fee|tax|"
    r"discount|revenue|sales|spend|charge|payment|principal|interest|gross|net|margin|"
    r"balance|volume|weight|duration|score)($|_)", re.I)
NON_ADDITIVE_RE = re.compile(
    r"(^|_)(balance|level|stock|position|rate|pct|percent|percentage|ratio|avg|average|mean|"
    r"median|price|score|index)($|_)", re.I)
DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d %b %Y", "%d-%b-%Y",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m", "%Y%m%d")


def looks_like_date(raw: str) -> bool:
    text = raw.strip()
    if not text or len(text) > 32:
        return False
    for fmt in DATE_FORMATS:
        try:
            datetime.strptime(text[:19] if len(fmt) > 10 else text, fmt)
            return True
        except ValueError:
            continue
    return False


class Column:
    """One column's statistics and the role they imply."""

    def __init__(self, name: str, raw: list[str]) -> None:
        self.name = name
        self.rows = len(raw)
        self.filled = [v.strip() for v in raw if v.strip()]
        self.nulls = self.rows - len(self.filled)
        self.counts = Counter(self.filled)
        self.distinct = len(self.counts)
        self.numbers = [d for d in (to_decimal(v) for v in self.filled) if d is not None]
        self.numeric = bool(self.filled) and len(self.numbers) >= 0.9 * len(self.filled)
        self.dates = sum(looks_like_date(v) for v in self.filled[:2000])
        self.temporal = bool(self.filled) and self.dates >= 0.9 * min(len(self.filled), 2000)
        self.avg_len = sum(len(v) for v in self.filled) / len(self.filled) if self.filled else 0
        self.role, self.notes = self._classify()

    def _classify(self) -> tuple[str, list[str]]:
        notes: list[str] = []
        if not self.filled:
            return "empty", ["no values at all — it cannot support any comparison"]
        if self.distinct == 1:
            return "constant", [f"one value everywhere ({next(iter(self.counts))!r}) — "
                                "often the fingerprint of the filter that produced the file"]
        if METADATA_RE.search(self.name):
            notes.append("lineage/audit: group differing rows by this first — one batch, load or "
                         "source usually carries the whole gap")
            return "metadata", notes
        if self.temporal:
            notes.append("check which time this is (event, effective, posted, or load) — the "
                         "filter that built the file used exactly one of them")
            return "temporal", notes

        measure_name = bool(MEASURE_RE.search(self.name))
        identity_name = bool(IDENTITY_RE.search(self.name))
        unique = self.distinct == len(self.filled) and self.nulls == 0
        whole = self.numeric and all(n == n.to_integral_value() for n in self.numbers)

        if self.numeric and measure_name and not identity_name:
            return "measure", notes + self._measure_notes()
        if unique and (identity_name or not self.numeric or whole):
            notes.append("unique and non-null — a candidate key for the join")
            if self.numeric:
                notes.append("numeric-looking id: load it as text, or leading zeros and long "
                             "digits will be destroyed")
            return "identity", notes
        if self.numeric and (measure_name or self.distinct > 20 or not whole):
            return "measure", notes + self._measure_notes()
        if self.avg_len > 25 and self.distinct > 0.9 * len(self.filled):
            return "free text", ["not comparable directly; use it as evidence when reading examples"]
        if self.distinct <= 10:
            notes.append("low cardinality — slice the difference by this; a gap that sits in one "
                         "value is a mechanism, not scattered error")
            return "flag/status", notes
        if self.distinct <= 50:
            notes.append("a dimension — attribute the gap across it")
            return "dimension", notes
        return "descriptive", ["high cardinality — useful for identifying a row, not for grouping"]

    def _measure_notes(self) -> list[str]:
        notes: list[str] = []
        if NON_ADDITIVE_RE.search(self.name):
            notes.append("probably NOT additive — summing a balance, rate or price across rows "
                         "or periods produces a number that means nothing")
        neg = sum(1 for n in self.numbers if n < 0)
        zero = sum(1 for n in self.numbers if n == 0)
        if neg:
            notes.append(f"{neg:,} negative values — confirm the sign convention before totalling")
        if zero:
            notes.append(f"{zero:,} zeros — they move counts without moving sums")
        return notes

    def summary(self) -> str:
        null_pct = self.nulls / self.rows * 100 if self.rows else 0
        span = ""
        if self.numeric and self.numbers:
            span = f"  min {money(min(self.numbers))}  max {money(max(self.numbers))}"
        elif self.filled:
            lo, hi = min(self.filled), max(self.filled)
            span = f"  first {lo[:18]!r}  last {hi[:18]!r}"
        return (f"{self.name:<24} {self.role:<12} {self.distinct:>8,} distinct  "
                f"{null_pct:>5.1f}% null{span}")


def functional_dependencies(rows: list[Row], cols: list[str], max_card: int) -> list[str]:
    """A -> B when every value of A carries exactly one value of B."""
    found = []
    cardinality = {c: len({r.get(c, "") for r in rows}) for c in cols}
    candidates = [c for c in cols if 1 < cardinality[c] <= max_card]
    for a in candidates:
        if cardinality[a] == len(rows):
            continue  # a unique column determines every other column by definition
        for b in candidates:
            if a == b:
                continue
            mapping: dict[str, str] = {}
            ok = True
            for r in rows:
                av, bv = r.get(a, ""), r.get(b, "")
                if mapping.setdefault(av, bv) != bv:
                    ok = False
                    break
            if ok and len(mapping) > 1:
                found.append(f"{a} -> {b}  ({len(mapping):,} values of {a}, each with one {b})")
    return found


def derived_columns(rows: list[Row], numeric: list[str], tol: Decimal) -> list[str]:
    """Columns that are arithmetic on other columns: a = b+c, b-c, b*c, or k*b."""
    found: list[str] = []
    seen_triples: set[frozenset[str]] = set()
    parsed = {c: [to_decimal(r.get(c, "")) for r in rows] for c in numeric}

    def holds(a: str, fn) -> bool:
        checked = 0
        for i in range(len(rows)):
            va = parsed[a][i]
            try:
                expected = fn(i)
            except (TypeError, ZeroDivisionError):
                return False
            if va is None or expected is None:
                continue
            if abs(va - expected) > tol:
                return False
            checked += 1
        return checked >= max(3, len(rows) // 10)

    for a in numeric:
        for b in numeric:
            if b == a:
                continue
            if numeric.index(a) < numeric.index(b):  # a ratio and its inverse are one finding
                ratios = [parsed[a][i] / parsed[b][i] for i in range(len(rows))
                          if parsed[a][i] is not None and parsed[b][i] not in (None, 0)]
                if len(ratios) >= 3 and len(set(ratios)) == 1 and ratios[0] not in (0, 1):
                    found.append(f"{a} = {round(ratios[0], 8).normalize():f} * {b}  "
                                 f"(a fixed multiple — units, tax, or FX applied at load)")
            for c in numeric:
                if c in (a, b) or numeric.index(c) < numeric.index(b):
                    continue
                for symbol, fn in (("+", lambda i, b=b, c=c: (parsed[b][i] + parsed[c][i])
                                    if None not in (parsed[b][i], parsed[c][i]) else None),
                                   ("*", lambda i, b=b, c=c: (parsed[b][i] * parsed[c][i])
                                    if None not in (parsed[b][i], parsed[c][i]) else None)):
                    if holds(a, fn) and frozenset((a, b, c)) not in seen_triples:
                        seen_triples.add(frozenset((a, b, c)))
                        found.append(f"{a} = {b} {symbol} {c}  (recompute it on each side: a side that "
                                     f"fails its own arithmetic is the wrong side)")
            for b2 in numeric:
                if b2 in (a, b):
                    continue
                if frozenset((a, b, b2)) in seen_triples:
                    continue
                if holds(a, lambda i, b=b, c=b2: (parsed[b][i] - parsed[c][i])
                         if None not in (parsed[b][i], parsed[c][i]) else None):
                    seen_triples.add(frozenset((a, b, b2)))
                    found.append(f"{a} = {b} - {b2}  (recompute it on each side)")
    return sorted(set(found))


def near_duplicates(rows: list[Row], numeric: list[str]) -> list[str]:
    """Numeric columns that move together — often the same fact twice, rescaled."""
    found = []
    series = {}
    for c in numeric:
        vals = [to_decimal(r.get(c, "")) for r in rows]
        series[c] = [float(v) if v is not None else None for v in vals]
    for i, a in enumerate(numeric):
        for b in numeric[i + 1:]:
            pairs = [(x, y) for x, y in zip(series[a], series[b]) if x is not None and y is not None]
            if len(pairs) < 5:
                continue
            n = len(pairs)
            mx, my = sum(x for x, _ in pairs) / n, sum(y for _, y in pairs) / n
            sxy = sum((x - mx) * (y - my) for x, y in pairs)
            sxx = sum((x - mx) ** 2 for x, _ in pairs)
            syy = sum((y - my) ** 2 for _, y in pairs)
            if sxx <= 0 or syy <= 0:
                continue
            r = sxy / (sxx * syy) ** 0.5
            if abs(r) > 0.999:
                found.append(f"{a} and {b} move together (r={r:+.4f}) — likely the same fact twice; "
                             f"totalling both double-counts")
    return found


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--file", action="append", required=True, type=Path,
                   help="File to profile (repeat to compare the same columns across files)")
    p.add_argument("--sheet", default=None, help="Worksheet name for .xlsx inputs")
    p.add_argument("--delimiter", default=None, help="CSV delimiter (default: sniff , vs tab)")
    p.add_argument("--key", action="append", default=[], help="Key you intend to join on, to be checked")
    p.add_argument("--sample-values", type=int, default=3, help="Top values to show per column (default 3)")
    p.add_argument("--max-cardinality", type=int, default=50, help="Cardinality cap for dependency search")
    p.add_argument("--tol", default="0.005", help="Tolerance for derived-column arithmetic (default 0.005)")
    p.add_argument("--json", type=Path, default=None, help="Write the profile as JSON")
    args = p.parse_args(argv)

    out = print
    report: dict[str, Any] = {}
    profiles: dict[str, dict[str, Column]] = {}

    for path in args.file:
        cols, rows = load(path, args.sheet, args.delimiter)
        sample = rows[:SAMPLE_LIMIT]
        profile = {c: Column(c, [r.get(c, "") for r in rows]) for c in cols}
        profiles[str(path)] = profile

        out(f"\n=== {path}  {len(rows):,} rows x {len(cols)} columns " + "=" * 20)
        out(f"{'column':<24} {'role':<12} {'distinct':>16}  {'null':>6}")
        for c in cols:
            out("  " + profile[c].summary())

        out("\n--- what each column is for " + "-" * 42)
        for c in cols:
            col = profile[c]
            top = ", ".join(f"{v!r} ({n / max(1, len(col.filled)) * 100:.0f}%)"
                            for v, n in col.counts.most_common(args.sample_values))
            out(f"  {c} [{col.role}]")
            if top:
                out(f"    most common: {top}")
            for note in col.notes:
                out(f"    - {note}")

        roles: dict[str, list[str]] = defaultdict(list)
        for c in cols:
            roles[profile[c].role].append(c)
        out("\n--- how to use them in a reconciliation " + "-" * 31)
        out(f"  join on:            {', '.join(roles['identity']) or '(no unique column — build a composite key)'}")
        out(f"  compare:            {', '.join(roles['measure']) or '(none detected)'}")
        out(f"  slice the gap by:   {', '.join(roles['flag/status'] + roles['dimension']) or '(none)'}")
        out(f"  date/vintage:       {', '.join(roles['temporal']) or '(none)'}")
        out(f"  explains bad loads: {', '.join(roles['metadata']) or '(none)'}")
        if roles["constant"]:
            out(f"  constant here:      {', '.join(roles['constant'])} "
                f"— check whether the other side is constant too, and at the same value")

        if args.key:
            out("\n--- the key you intend to join on " + "-" * 37)
            missing = [k for k in args.key if k not in cols]
            if missing:
                out(f"  !  not in this file: {', '.join(missing)}")
            present = [k for k in args.key if k in cols]
            if present:
                seen = Counter(tuple(r.get(k, "").strip() for k in present) for r in rows)
                dups = {k: n for k, n in seen.items() if n > 1}
                blanks = sum(1 for k in seen if any(part == "" for part in k))
                out(f"  {' + '.join(present)}: {len(seen):,} distinct, {len(dups):,} duplicated, "
                    f"{blanks:,} with a blank part")
                if dups:
                    out(f"  !  not unique — a join on it fans out and multiplies every total")
                    for k, n in sorted(dups.items(), key=lambda kv: -kv[1])[:5]:
                        out(f"     x{n}: {'|'.join(k)}")

        singles = [c for c in cols if profile[c].distinct == len(rows) and profile[c].nulls == 0]
        out("\n--- candidate keys " + "-" * 52)
        out(f"  unique on its own: {', '.join(singles) if singles else '(none)'}")
        if not singles:
            groupable = [c for c in cols if 1 < profile[c].distinct < len(rows)]
            pairs = [(a, b) for i, a in enumerate(groupable) for b in groupable[i + 1:]
                     if len({(r.get(a, ""), r.get(b, "")) for r in rows}) == len(rows)]
            out(f"  unique as a pair:  {', '.join(f'{a}+{b}' for a, b in pairs[:5]) if pairs else '(none found)'}")

        deps = functional_dependencies(sample, cols, args.max_cardinality)
        if deps:
            out("\n--- one column determines another " + "-" * 37)
            for d in deps[:15]:
                out(f"  {d}")
            out("  a dependency that holds here and breaks on the other side is a finding, "
                "not a coincidence")

        numeric = [c for c in cols if profile[c].numeric and profile[c].distinct > 1][:10]
        derived = derived_columns(sample[:2000], numeric, Decimal(args.tol))
        if derived:
            out("\n--- columns computed from other columns " + "-" * 31)
            for d in derived[:12]:
                out(f"  {d}")
        dupes = near_duplicates(sample[:5000], numeric)
        if dupes:
            out("\n--- columns that carry the same fact " + "-" * 34)
            for d in dupes[:10]:
                out(f"  {d}")

        report[str(path)] = {
            c: {"role": profile[c].role, "distinct": profile[c].distinct, "nulls": profile[c].nulls,
                "numeric": profile[c].numeric, "temporal": profile[c].temporal,
                "top": profile[c].counts.most_common(args.sample_values), "notes": profile[c].notes}
            for c in cols
        }
        report[str(path)]["_dependencies"] = deps[:15]
        report[str(path)]["_derived"] = derived[:12]

    if len(args.file) > 1:
        out("\n=== the same column name across files " + "=" * 33)
        names = [str(f) for f in args.file]
        shared = set.intersection(*(set(profiles[n]) for n in names))
        out(f"{'column':<20}" + "".join(f"{Path(n).name[:20]:>22}" for n in names))
        for c in sorted(shared):
            cells = []
            for n in names:
                col = profiles[n][c]
                cells.append(f"{col.role}/{col.distinct:,}d/{col.nulls / max(1, col.rows) * 100:.0f}%n")
            out(f"  {c:<18}" + "".join(f"{cell:>22}" for cell in cells))
            roles = {profiles[n][c].role for n in names}
            if len(roles) > 1:
                out(f"    !  different roles across files ({', '.join(sorted(roles))}) — the same name "
                    f"does not mean the same thing")
        for n in names:
            extra = set(profiles[n]) - shared
            if extra:
                out(f"  only in {Path(n).name}: {', '.join(sorted(extra))}")

    if args.json:
        args.json.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        out(f"\nJSON profile written to {args.json}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        sys.stderr.close()
        raise SystemExit(0)
