#!/usr/bin/env python3
"""Track keys, values and columns across many files — periods or vintages.

A reconciliation is rarely two files. It is twelve monthly exports, or the same
period re-exported four times, and the interesting facts live between the
files: a period that is missing, a row that quietly changed value in a later
export, a column that is stable in every file but one.

    python track_across_files.py --files "exports/*.csv" --key order_id --value amount
    python track_across_files.py --files "vintages/*.xlsx" --key order_id --lookup ORD-00417

It reports the file inventory and the period sequence, says whether the set is
a timeline or repeated vintages of one population, totals each period with its
step change, tracks key churn, finds restatements (the same key with a
different value in a later file), and — with --lookup — prints one row's whole
history across the files, marking what changed at each appearance.

Stdlib only, via tabular.py.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Sequence

from tabular import Row, key_of, load, money, normalise_key, numeric_columns, to_decimal

PERIOD_PATTERNS = (
    re.compile(r"(\d{4}-\d{2}-\d{2})"), re.compile(r"(\d{4}-\d{2})"), re.compile(r"(\d{4}Q[1-4])", re.I),
    re.compile(r"(\d{4})[-_]?(\d{2})[-_]?(\d{2})"), re.compile(r"(\d{6})(?!\d)"), re.compile(r"(\d{4})(?!\d)"),
)


def period_of(path: Path, rows: list[Row], column: str | None, pattern: str | None) -> str:
    """A file's period: from a column if given, else from its name, else the name itself."""
    if column:
        values = {str(r.get(column, "")).strip()[:10] for r in rows if str(r.get(column, "")).strip()}
        if len(values) == 1:
            return next(iter(values))
        if values:
            return f"{min(values)}..{max(values)}"
    if pattern:
        m = re.search(pattern, path.name)
        if m:
            return m.group(1) if m.groups() else m.group(0)
    for rx in PERIOD_PATTERNS:
        m = rx.search(path.name)
        if m:
            return "-".join(g for g in m.groups() if g) if len(m.groups()) > 1 else m.group(1)
    return path.stem


def expected_months(periods: Sequence[str]) -> list[str]:
    """Fill the month sequence between the first and last YYYY-MM period."""
    months = sorted({p[:7] for p in periods if re.fullmatch(r"\d{4}-\d{2}.*", p)})
    if len(months) < 2:
        return []
    start, end = months[0], months[-1]
    year, month = int(start[:4]), int(start[5:7])
    out = []
    while f"{year:04d}-{month:02d}" <= end:
        out.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--files", action="append", required=True, help="File path or glob (repeatable)")
    p.add_argument("--key", action="append", default=[], help="Key column (repeat for a composite key)")
    p.add_argument("--value", action="append", default=[], help="Numeric column to track (default: auto-detect)")
    p.add_argument("--period-column", default=None, help="Column holding the period, instead of the filename")
    p.add_argument("--period-regex", default=None, help="Regex capturing the period from the filename")
    p.add_argument("--lookup", action="append", default=[], help="Print one key's history across the files")
    p.add_argument("--sheet", default=None, help="Worksheet name for .xlsx inputs")
    p.add_argument("--delimiter", default=None, help="CSV delimiter (default: sniff , vs tab)")
    p.add_argument("--normalize-keys", action="store_true", help="Case/whitespace/leading-zero insensitive keys")
    p.add_argument("--abs-tol", default="0.005", help="Tolerance for calling a value restated (default 0.005)")
    p.add_argument("--sample", type=int, default=5, help="Examples to print per finding (default 5)")
    p.add_argument("--json", type=Path, default=None, help="Write the full report as JSON")
    args = p.parse_args(argv)

    paths: list[Path] = []
    for spec in args.files:
        hits = sorted(glob.glob(spec))
        paths.extend(Path(h) for h in hits) if hits else paths.append(Path(spec))
    paths = [p for p in paths if p.is_file()]
    if len(paths) < 2:
        raise SystemExit("give at least two files — one file is a job for reconcile.py or profile_columns.py")

    abs_tol = Decimal(args.abs_tol)
    out = print
    findings: list[str] = []
    report: dict[str, Any] = {}

    loaded: list[tuple[Path, str, list[str], list[Row]]] = []
    for path in paths:
        cols, rows = load(path, args.sheet, args.delimiter)
        loaded.append((path, period_of(path, rows, args.period_column, args.period_regex), cols, rows))
    loaded.sort(key=lambda item: (item[1], item[0].name))

    common = [c for c in loaded[0][2] if all(c in cols for _, _, cols, _ in loaded)]
    keys = args.key or ([common[0]] if common else [])
    if not keys or any(k not in common for k in keys):
        raise SystemExit(f"key column(s) must exist in every file. Shared columns: {', '.join(common) or '(none)'}")
    values = args.value or numeric_columns(common, *[rows for _, _, _, rows in loaded], exclude=set(keys))
    if not values:
        raise SystemExit("no numeric column present in every file; pass --value explicitly")

    # key -> [(period, path, sums, first row)] in file order
    history: dict[tuple[str, ...], list[tuple[str, Path, dict[str, Decimal], Row]]] = defaultdict(list)
    per_file: list[dict[str, Any]] = []

    out("\n=== files " + "=" * 61)
    out(f"{'period':<14}{'file':<28}{'rows':>10}{'keys':>10}   totals")
    for path, period, cols, rows in loaded:
        sums: dict[tuple[str, ...], dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
        firsts: dict[tuple[str, ...], Row] = {}
        for row in rows:
            k = key_of(row, keys, args.normalize_keys)
            firsts.setdefault(k, row)
            for col in values:
                parsed = to_decimal(row.get(col, ""))
                if parsed is not None:
                    sums[k][col] += parsed
        totals = {col: sum((s[col] for s in sums.values()), Decimal(0)) for col in values}
        out(f"{period:<14}{path.name[:26]:<28}{len(rows):>10,}{len(sums):>10,}   "
            + "  ".join(f"{c}={money(v)}" for c, v in totals.items()))
        for k, s in sums.items():
            history[k].append((period, path, dict(s), firsts[k]))
        per_file.append({"path": str(path), "period": period, "rows": len(rows), "keys": len(sums),
                         "totals": {c: str(v) for c, v in totals.items()}})
        missing_cols = [c for c in loaded[0][2] if c not in cols]
        if missing_cols:
            out(f"{'':<14}!  missing columns: {', '.join(missing_cols)}")
            findings.append(f"{path.name} is missing columns present in the first file: {', '.join(missing_cols)}")
    report["files"] = per_file

    periods = [period for _, period, _, _ in loaded]
    key_sets = []
    for path, period, cols, rows in loaded:
        key_sets.append({key_of(r, keys, args.normalize_keys) for r in rows})
    overlaps = []
    for i in range(len(key_sets) - 1):
        a, b = key_sets[i], key_sets[i + 1]
        overlaps.append(len(a & b) / max(1, min(len(a), len(b))))
    mean_overlap = sum(overlaps) / len(overlaps) if overlaps else 0

    out("\n=== what kind of set this is " + "=" * 42)
    out(f"consecutive files share {mean_overlap * 100:.1f}% of their keys on average")
    if mean_overlap < 0.2:
        shape = ("a timeline: each file is a different population, so compare the series "
                 "period over period, not row by row")
    elif mean_overlap > 0.8:
        shape = ("vintages of one population: the same rows re-exported, so the question is "
                 "what got restated between them")
    else:
        shape = ("overlapping windows: files share part of their population — dedupe before "
                 "totalling the union, or rows will be counted twice")
        findings.append("files overlap partially — the union will double-count shared keys unless deduped")
    out(f"looks like {shape}")
    report["shape"] = {"mean_overlap": mean_overlap, "reading": shape}

    out("\n=== period sequence " + "=" * 51)
    duplicate_periods = [p for p, n in Counter(periods).items() if n > 1]
    out(f"periods: {', '.join(periods)}")
    if duplicate_periods:
        out(f"!  more than one file for: {', '.join(duplicate_periods)} — a re-export, or double counting")
        findings.append(f"{len(duplicate_periods)} period(s) appear in more than one file")
    expected = expected_months(periods)
    if expected:
        gaps = [m for m in expected if not any(p.startswith(m) for p in periods)]
        if gaps:
            out(f"!  no file for: {', '.join(gaps)} — a gap in the timeline, not an empty month")
            findings.append(f"missing period(s): {', '.join(gaps)}")
        else:
            out(f"the month sequence {expected[0]}..{expected[-1]} is complete")

    out("\n=== totals by period " + "=" * 50)
    for col in values:
        out(f"  {col}:")
        previous: Decimal | None = None
        steps: list[tuple[str, Decimal, Decimal]] = []
        for entry in per_file:
            total = Decimal(entry["totals"][col])
            delta = total - previous if previous is not None else None
            pct = (f"{delta / previous * 100:+.1f}%" if previous not in (None, 0) and delta is not None else "")
            out(f"    {entry['period']:<14}{money(total):>18}"
                + (f"   {money(delta):>16}  {pct:>8}" if delta is not None else ""))
            if delta is not None:
                steps.append((entry["period"], delta, total))
            previous = total
        if len(steps) >= 2:
            biggest = max(steps, key=lambda s: abs(s[1]))
            others = sorted(abs(s[1]) for s in steps if s is not biggest)
            typical = others[len(others) // 2] if others else Decimal(0)
            if typical and abs(biggest[1]) > 5 * typical:
                note = (f"{col}: the step into {biggest[0]} is {money(biggest[1])}, "
                        f"{abs(biggest[1]) / typical:.0f}x the typical period-over-period move — "
                        f"a step change dates a cause to that period")
                out(f"    ^ {note}")
                findings.append(note)

    out("\n=== key churn " + "=" * 57)
    out(f"{'from -> to':<32}{'carried':>10}{'new':>10}{'dropped':>10}")
    for i in range(len(loaded) - 1):
        a, b = key_sets[i], key_sets[i + 1]
        out(f"{periods[i] + ' -> ' + periods[i + 1]:<32}{len(a & b):>10,}{len(b - a):>10,}{len(a - b):>10,}")
    always = set.intersection(*key_sets) if key_sets else set()
    out(f"keys present in every file: {len(always):,}")
    report["churn"] = {"present_in_all": len(always)}

    out("\n=== restatements: the same key, a different number later " + "=" * 14)
    restated: dict[str, list[tuple[tuple[str, ...], str, Decimal, str, Decimal]]] = defaultdict(list)
    round_trips: Counter[str] = Counter()
    for k, appearances in history.items():
        if len(appearances) < 2:
            continue
        for col in values:
            series = [(period, sums.get(col, Decimal(0))) for period, _, sums, _ in appearances]
            moves = sum(1 for i in range(1, len(series)) if abs(series[i][1] - series[i - 1][1]) > abs_tol)
            if not moves:
                continue
            (first_period, a), (last_period, b) = series[0], series[-1]
            restated[col].append((k, first_period, a, last_period, b))
            if abs(b - a) <= abs_tol:  # changed and changed back: invisible in a first-vs-last check
                round_trips[col] += 1
    if not any(restated.values()):
        out("  none — every key that appears more than once carries the same value throughout")
    for col, items in restated.items():
        net = sum((b - a for _, _, a, _, b in items), Decimal(0))
        out(f"  {col}: {len(items):,} keys restated, net {money(net)}"
            + (f", of which {round_trips[col]:,} changed and changed back "
               f"(invisible if you only compare the first and last file)" if round_trips[col] else ""))
        findings.append(f"{col}: {len(items):,} keys changed value between files, net {money(net)} "
                        f"— fix a vintage before reconciling, or the answer moves under you")
        for k, fp, a, lp, b in sorted(items, key=lambda r: -abs(r[4] - r[2]))[: args.sample]:
            out(f"    {'|'.join(k):<24} {fp} {money(a):>14}  ->  {lp} {money(b):>14}  "
                f"({money(b - a)})")
    report["restatements"] = {col: len(items) for col, items in restated.items()}

    described = [c for c in common if c not in set(keys) | set(values)]
    repeated = sum(1 for appearances in history.values() if len(appearances) > 1)
    if described and not repeated:
        out("\n=== descriptive columns that change between files " + "=" * 21)
        out("  no key appears in more than one file, so there is nothing to compare across them")
    if described and repeated:
        out("\n=== descriptive columns that change between files " + "=" * 21)
        churn: dict[str, int] = {}
        for col in described:
            changed = 0
            example = None
            for k, appearances in history.items():
                if len(appearances) < 2:
                    continue
                seen = {normalise_key(row.get(col, "")) for _, _, _, row in appearances}
                if len(seen) > 1:
                    changed += 1
                    example = example or (k, [(period, row.get(col, "")) for period, _, _, row in appearances])
            churn[col] = changed
            verdict = "stable" if not changed else f"{changed:,} keys change value"
            out(f"  {col:<24} {verdict}")
            if example:
                k, trail = example
                out(f"    e.g. {'|'.join(k)}: " + " -> ".join(f"{p}:{v!r}" for p, v in trail[: args.sample]))
        mutable = [c for c, n in churn.items() if n]
        if mutable:
            findings.append(f"descriptive column(s) {', '.join(mutable)} change between files — "
                            f"joining to the latest value rewrites history; join as-of the period instead")
        report["descriptive_churn"] = churn

    for wanted in args.lookup:
        target = key_of({keys[0]: wanted}, keys[:1], args.normalize_keys) if len(keys) == 1 else None
        matches = [k for k in history if (k == target) or wanted in "|".join(k)
                   or normalise_key(wanted) in "|".join(normalise_key(part) for part in k)]
        out(f"\n=== history of {wanted!r} " + "=" * max(4, 52 - len(wanted)))
        if not matches:
            out("  never appears in any of these files")
            continue
        for k in matches[:3]:
            appearances = history[k]
            out(f"  key {'|'.join(k)} — in {len(appearances)} of {len(loaded)} files")
            previous: Row | None = None
            for period, path, sums, row in appearances:
                changes = []
                if previous is not None:
                    changes = [f"{c}: {previous.get(c, '')!r} -> {row.get(c, '')!r}"
                               for c in common if normalise_key(previous.get(c, "")) != normalise_key(row.get(c, ""))]
                out(f"    {period:<12} {path.name[:24]:<26} "
                    + "  ".join(f"{c}={money(sums.get(c, Decimal(0)))}" for c in values)
                    + ("   [first appearance]" if previous is None else
                       ("   changed: " + "; ".join(changes) if changes else "   unchanged")))
                previous = row
            gaps = [p for p in periods if p not in {a[0] for a in appearances}]
            if gaps:
                out(f"    absent from: {', '.join(gaps)}")

    out("\n=== verdict " + "=" * 59)
    if not findings:
        out("the set is complete and consistent: no gaps, no duplicate periods, no restatements,")
        out("and no descriptive column changed between files.")
    else:
        for f in findings:
            out(f"  - {f}")
        out("\nnext: fix a vintage and a period before reconciling any pair of these files,")
        out("and carry the period into the key if a row can appear in more than one.")
    report["findings"] = findings

    if args.json:
        args.json.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        out(f"\nJSON report written to {args.json}")
    return 1 if findings else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        sys.stderr.close()
        raise SystemExit(0)
