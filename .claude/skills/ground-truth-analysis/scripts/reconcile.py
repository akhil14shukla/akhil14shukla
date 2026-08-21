#!/usr/bin/env python3
"""Reconcile two tables against each other and print a closing bridge.

The structural layers of a reconciliation — schema, key uniqueness, coverage,
totals, row-level differences — are mechanical, and doing them by hand is where
silent join fan-out and float noise get mistaken for findings. This runs them
in order, in exact decimal arithmetic, and decomposes the total gap into
missing rows, extra rows and value differences so the parts sum to the whole.

    python reconcile.py --truth ledger.csv --candidate export.xlsx \
        --key order_id --value amount --abs-tol 0.005

    python reconcile.py --truth a.csv --candidate b.csv \
        --key entity --key period --normalize-keys --json report.json

Stdlib only. Reads CSV/TSV and basic .xlsx. It answers "what differs", not
"why" — take its output back to the hypothesis catalogue for the cause.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
import zipfile
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Sequence

Row = dict[str, str]

# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #

EXCEL_EPOCH = date(1899, 12, 30)  # Excel's day 1 is 1900-01-01, with a leap bug
DATE_FMT_IDS = set(range(14, 23)) | set(range(27, 37)) | set(range(45, 48)) | set(range(50, 59))


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _col_index(ref: str) -> int:
    """'BC12' -> 54 (zero-based column index)."""
    n = 0
    for ch in ref:
        if not ch.isalpha():
            break
        n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1


def load_xlsx(path: Path, sheet: str | None) -> list[list[str]]:
    """Read a worksheet into rows of strings. Dates come back as ISO strings."""
    import xml.etree.ElementTree as ET

    with zipfile.ZipFile(path) as z:
        names = z.namelist()

        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")):
                shared.append("".join(t.text or "" for t in si.iter() if _local(t.tag) == "t"))

        date_styles: set[int] = set()
        if "xl/styles.xml" in names:
            root = ET.fromstring(z.read("xl/styles.xml"))
            custom = {
                int(n.get("numFmtId", "0")): n.get("formatCode", "")
                for n in root.iter()
                if _local(n.tag) == "numFmt"
            }
            xfs = next((c for c in root if _local(c.tag) == "cellXfs"), [])
            for i, xf in enumerate(xfs):
                fmt_id = int(xf.get("numFmtId", "0"))
                code = re.sub(r'"[^"]*"|\[[^\]]*\]', "", custom.get(fmt_id, ""))
                if fmt_id in DATE_FMT_IDS or re.search(r"[ymdhs]", code):
                    date_styles.add(i)

        wb = ET.fromstring(z.read("xl/workbook.xml"))
        sheets = [s for s in wb.iter() if _local(s.tag) == "sheet"]
        rels = {}
        if "xl/_rels/workbook.xml.rels" in names:
            for rel in ET.fromstring(z.read("xl/_rels/workbook.xml.rels")):
                rels[rel.get("Id")] = rel.get("Target", "").lstrip("/")
        if not sheets:
            raise SystemExit(f"{path}: no worksheets found")
        chosen = sheets[0]
        if sheet is not None:
            match = [s for s in sheets if s.get("name") == sheet]
            if not match:
                have = ", ".join(s.get("name", "?") for s in sheets)
                raise SystemExit(f"{path}: no sheet named {sheet!r}. Sheets: {have}")
            chosen = match[0]
        rid = next((v for k, v in chosen.attrib.items() if _local(k) == "id"), None)
        target = rels.get(rid, "worksheets/sheet1.xml")
        member = target if target.startswith("xl/") else f"xl/{target}"
        if member not in names:
            member = next(n for n in names if n.startswith("xl/worksheets/"))

        rows: list[list[str]] = []
        for r in ET.fromstring(z.read(member)).iter():
            if _local(r.tag) != "row":
                continue
            cells: dict[int, str] = {}
            for c in r:
                if _local(c.tag) != "c":
                    continue
                idx = _col_index(c.get("r", "")) if c.get("r") else len(cells)
                ctype = c.get("t", "n")
                text = ""
                for child in c:
                    if _local(child.tag) == "v":
                        text = child.text or ""
                    elif _local(child.tag) == "is":
                        text = "".join(t.text or "" for t in child.iter() if _local(t.tag) == "t")
                if ctype == "s" and text:
                    text = shared[int(text)]
                elif ctype == "b" and text:
                    text = "TRUE" if text == "1" else "FALSE"
                elif ctype == "n" and text and int(c.get("s", "-1") or -1) in date_styles:
                    try:
                        serial = float(text)
                        stamp = EXCEL_EPOCH + timedelta(days=serial)
                        text = stamp.isoformat() if serial % 1 else stamp.isoformat()[:10]
                    except (ValueError, OverflowError):
                        pass
                cells[idx] = text
            width = max(cells) + 1 if cells else 0
            rows.append([cells.get(i, "") for i in range(width)])
        return rows


def load(path: Path, sheet: str | None, delimiter: str | None) -> tuple[list[str], list[Row]]:
    if path.suffix.lower() in {".xlsx", ".xlsm"}:
        raw = load_xlsx(path, sheet)
    else:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        if delimiter is None:
            head = text.split("\n", 1)[0]
            delimiter = "\t" if head.count("\t") > head.count(",") else ","
        raw = [r for r in csv.reader(text.splitlines(), delimiter=delimiter)]
    raw = [r for r in raw if any(str(c).strip() for c in r)]  # drop blank rows
    if not raw:
        raise SystemExit(f"{path}: no data rows")
    header = [str(h).strip() for h in raw[0]]
    rows = [dict(zip(header, [str(c) for c in r] + [""] * (len(header) - len(r)))) for r in raw[1:]]
    return header, rows


# --------------------------------------------------------------------------- #
# Parsing and normalising
# --------------------------------------------------------------------------- #

CURRENCY = "$€£¥₹"


def to_decimal(raw: str) -> Decimal | None:
    """Parse a spreadsheet-shaped number. Returns None if it is not one."""
    s = unicodedata.normalize("NFKC", str(raw)).strip().replace(" ", "")
    if not s:
        return None
    s = s.replace("−", "-")
    negative = s.startswith("(") and s.endswith(")")
    if negative:
        s = s[1:-1]
    for ch in CURRENCY + " ":
        s = s.replace(ch, "")
    percent = s.endswith("%")
    s = s.rstrip("%")
    if s.count(",") and s.count("."):  # 1,234.56 vs 1.234,56
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(,\d{3})+", s):
        s = s.replace(",", "")
    elif s.count(",") == 1 and len(s.split(",")[1]) != 3:
        s = s.replace(",", ".")
    try:
        value = Decimal(s)
    except (InvalidOperation, ValueError):
        return None
    if percent:
        value /= 100
    return -value if negative else value


def normalise_key(raw: str) -> str:
    s = unicodedata.normalize("NFKC", str(raw)).strip().replace(" ", " ")
    s = re.sub(r"\s+", " ", s).casefold()
    if re.fullmatch(r"-?\d+\.0+", s):  # 1234.0 <- an ID read as a float
        s = s.split(".")[0]
    if re.fullmatch(r"0+\d+", s):  # 00742 <- a zero-padded code
        s = s.lstrip("0")
    return s


def key_of(row: Row, keys: Sequence[str], normalise: bool) -> tuple[str, ...]:
    return tuple(normalise_key(row.get(k, "")) if normalise else str(row.get(k, "")).strip() for k in keys)


# --------------------------------------------------------------------------- #
# Analysis
# --------------------------------------------------------------------------- #


def detect_value_columns(cols: Iterable[str], truth: list[Row], cand: list[Row], keys: set[str]) -> list[str]:
    """Columns that parse as numbers in at least 90% of non-empty cells on both sides."""
    found = []
    for col in cols:
        if col in keys:
            continue
        ok = True
        for rows in (truth, cand):
            filled = [r[col] for r in rows[:5000] if str(r.get(col, "")).strip()]
            if not filled or sum(to_decimal(v) is not None for v in filled) < 0.9 * len(filled):
                ok = False
                break
        if ok:
            found.append(col)
    return found


def aggregate(rows: list[Row], keys: Sequence[str], values: Sequence[str], normalise: bool):
    sums: dict[tuple[str, ...], dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    counts: Counter[tuple[str, ...]] = Counter()
    unparsed: Counter[str] = Counter()
    null_keys = 0
    for row in rows:
        k = key_of(row, keys, normalise)
        if any(part == "" for part in k):
            null_keys += 1
        counts[k] += 1
        for col in values:
            parsed = to_decimal(row.get(col, ""))
            if parsed is None:
                if str(row.get(col, "")).strip():
                    unparsed[col] += 1
            else:
                sums[k][col] += parsed
    return sums, counts, unparsed, null_keys


def close(a: Decimal, b: Decimal, abs_tol: Decimal, rel_tol: Decimal) -> bool:
    return abs(a - b) <= max(abs_tol, rel_tol * max(abs(a), abs(b)))


def pattern_scan(diffs: list[tuple[tuple[str, ...], Decimal, Decimal]], abs_tol: Decimal) -> list[str]:
    """Look for one mechanism behind many differences, rather than many errors."""
    notes: list[str] = []
    if len(diffs) < 3:  # a "pattern" over one or two rows is not a pattern
        return notes
    deltas = [c - t for _, t, c in diffs]
    ratios = [c / t for _, t, c in diffs if t != 0]

    if len(set(deltas)) == 1:
        notes.append(f"every difference is exactly {deltas[0]} — a constant offset, not per-row error")
    if ratios and len(ratios) > 1:
        lo, hi = min(ratios), max(ratios)
        if lo != 0 and (hi - lo) <= abs(lo) * Decimal("1e-6"):
            note = f"every candidate value is {format(lo.normalize(), 'f')} × the truth"
            for name, factor in (("a x1000 scale", 1000), ("a x100 scale", 100), ("a /100 scale", Decimal("0.01")),
                                 ("a sign flip", -1), ("a /1000 scale", Decimal("0.001"))):
                if abs(lo - Decimal(str(factor))) < Decimal("1e-9"):
                    note += f" — {name} difference, not a data problem"
                    break
            notes.append(note)
    if all(abs(d) <= Decimal("0.5") for d in deltas) and max(abs(d) for d in deltas) > abs_tol:
        notes.append("all differences are under half a unit — consistent with a rounding rule, "
                     "not with wrong values")
    if all(d > 0 for d in deltas) or all(d < 0 for d in deltas):
        notes.append(f"all {len(deltas)} differences are in the same direction — noise is two-sided, "
                     "so this is a mechanism")
    flipped = sum(1 for _, t, c in diffs if t != 0 and c == -t)
    if flipped:
        notes.append(f"{flipped} rows are exact sign flips — check the sign convention for those rows")
    return notes


def money(x: Decimal) -> str:
    return f"{x:,.4f}".rstrip("0").rstrip(".") if x % 1 else f"{x:,.0f}"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--truth", required=True, type=Path, help="The reference file")
    p.add_argument("--candidate", required=True, type=Path, help="The file being checked")
    p.add_argument("--key", action="append", default=[], help="Key column (repeat for a composite key)")
    p.add_argument("--value", action="append", default=[], help="Numeric column to compare (default: auto-detect)")
    p.add_argument("--map", action="append", default=[], metavar="CAND=TRUTH", help="Rename a candidate column")
    p.add_argument("--abs-tol", default="0.005", help="Absolute tolerance (default 0.005)")
    p.add_argument("--rel-tol", default="1e-9", help="Relative tolerance (default 1e-9)")
    p.add_argument("--normalize-keys", action="store_true", help="Case/whitespace/leading-zero insensitive keys")
    p.add_argument("--sheet", default=None, help="Worksheet name for .xlsx inputs")
    p.add_argument("--delimiter", default=None, help="CSV delimiter (default: sniff , vs tab)")
    p.add_argument("--sample", type=int, default=5, help="Example rows to print per finding (default 5)")
    p.add_argument("--json", type=Path, default=None, help="Write the full report as JSON")
    args = p.parse_args(argv)

    abs_tol, rel_tol = Decimal(args.abs_tol), Decimal(args.rel_tol)
    t_cols, t_rows = load(args.truth, args.sheet, args.delimiter)
    c_cols, c_rows = load(args.candidate, args.sheet, args.delimiter)

    renames = dict(m.split("=", 1) for m in args.map)
    if renames:
        c_rows = [{renames.get(k, k): v for k, v in r.items()} for r in c_rows]
        c_cols = [renames.get(c, c) for c in c_cols]

    report: dict[str, Any] = {"truth": str(args.truth), "candidate": str(args.candidate)}
    out = print

    out("\n=== L0/L1  inputs and schema " + "=" * 42)
    out(f"truth      {args.truth}   {len(t_rows):,} rows x {len(t_cols)} cols")
    out(f"candidate  {args.candidate}   {len(c_rows):,} rows x {len(c_cols)} cols")
    only_t, only_c = [c for c in t_cols if c not in c_cols], [c for c in c_cols if c not in t_cols]
    common = [c for c in t_cols if c in c_cols]
    if only_t:
        out(f"columns only in truth:      {', '.join(only_t)}")
    if only_c:
        out(f"columns only in candidate:  {', '.join(only_c)}")
    if not only_t and not only_c:
        out("columns identical on both sides")
    report["schema"] = {"only_truth": only_t, "only_candidate": only_c, "common": common}

    keys = args.key or ([common[0]] if common else [])
    if not keys:
        raise SystemExit("no shared columns; pass --key and --map explicitly")
    missing_key = [k for k in keys if k not in t_cols or k not in c_cols]
    if missing_key:
        raise SystemExit(f"key column(s) not present on both sides: {', '.join(missing_key)}")
    values = args.value or detect_value_columns(common, t_rows, c_rows, set(keys))
    if not values:
        raise SystemExit("no numeric columns found on both sides; pass --value explicitly")
    absent = [v for v in values if v not in t_cols or v not in c_cols]
    if absent:
        raise SystemExit(f"value column(s) not present on both sides: {', '.join(absent)} "
                         f"(use --map CAND=TRUTH if they are named differently)")
    out(f"key: {' + '.join(keys)}    comparing: {', '.join(values)}")
    if args.normalize_keys:
        out("keys normalised (case, whitespace, leading zeros, trailing .0)")

    t_sums, t_counts, t_unparsed, t_nullkeys = aggregate(t_rows, keys, values, args.normalize_keys)
    c_sums, c_counts, c_unparsed, c_nullkeys = aggregate(c_rows, keys, values, args.normalize_keys)
    for side, unparsed in (("truth", t_unparsed), ("candidate", c_unparsed)):
        for col, n in unparsed.items():
            out(f"!  {side}: {n:,} non-empty values in {col!r} did not parse as numbers "
                f"— they are excluded from every total below")

    out("\n=== L2  keys and grain " + "=" * 48)
    findings: list[str] = []
    for side, counts, nulls, rows in (("truth", t_counts, t_nullkeys, t_rows), ("candidate", c_counts, c_nullkeys, c_rows)):
        dups = {k: n for k, n in counts.items() if n > 1}
        out(f"{side:<10} {len(counts):,} distinct keys, {len(rows):,} rows, "
            f"{len(dups):,} duplicated keys" + (f", max multiplicity {max(dups.values())}" if dups else ""))
        if nulls:
            out(f"           !  {nulls:,} rows have an empty key part")
            findings.append(f"{side} has {nulls:,} rows with an empty key")
        if dups:
            findings.append(f"{side} keys are not unique ({len(dups):,} duplicated) — totals below are aggregated by key")
            for k, n in sorted(dups.items(), key=lambda kv: -kv[1])[: args.sample]:
                out(f"           dup x{n}: {'|'.join(k)}")
    if t_rows and c_rows:
        ratio = len(c_rows) / len(t_rows)
        if abs(ratio - round(ratio)) < 0.02 and round(ratio) > 1:
            findings.append(f"candidate has ~{round(ratio)}x the rows of truth — suspect a grain mismatch "
                            f"or a join fan-out before comparing values")
            out(f"!  row-count ratio {ratio:.3f} — near-integer, so check the grain first")
    report["keys"] = {"truth_distinct": len(t_counts), "candidate_distinct": len(c_counts),
                      "truth_dupes": sum(1 for n in t_counts.values() if n > 1),
                      "candidate_dupes": sum(1 for n in c_counts.values() if n > 1)}

    out("\n=== L3  coverage " + "=" * 54)
    t_keys, c_keys = set(t_sums), set(c_sums)
    matched, t_only, c_only = t_keys & c_keys, t_keys - c_keys, c_keys - t_keys
    out(f"matched keys        {len(matched):,}")
    out(f"truth only          {len(t_only):,}")
    out(f"candidate only      {len(c_only):,}")
    for label, ks, sums in (("truth only", t_only, t_sums), ("candidate only", c_only, c_sums)):
        for k in sorted(ks)[: args.sample]:
            out(f"  {label}: {'|'.join(k)}  " + "  ".join(f"{v}={money(sums[k][v])}" for v in values))
    if t_only:
        findings.append(f"{len(t_only):,} keys are missing from the candidate")
    if c_only:
        findings.append(f"{len(c_only):,} keys in the candidate are not in the truth")
    report["coverage"] = {"matched": len(matched), "truth_only": len(t_only), "candidate_only": len(c_only)}

    report["columns"] = {}
    for col in values:
        t_total = sum((s[col] for s in t_sums.values()), Decimal(0))
        c_total = sum((s[col] for s in c_sums.values()), Decimal(0))
        missing = sum((t_sums[k][col] for k in t_only), Decimal(0))
        extra = sum((c_sums[k][col] for k in c_only), Decimal(0))
        matched_diff = sum((c_sums[k][col] - t_sums[k][col] for k in matched), Decimal(0))
        residual = c_total - (t_total - missing + extra + matched_diff)

        out(f"\n=== L4  totals and bridge: {col} " + "=" * max(4, 44 - len(col)))
        gap = c_total - t_total
        pct = f"{gap / t_total * 100:+.4f}%" if t_total else "n/a"
        out(f"truth total      {money(t_total):>20}")
        out(f"candidate total  {money(c_total):>20}")
        out(f"difference       {money(gap):>20}   ({pct})")
        out("")
        bridge_rows = [
            ("truth", t_total),
            (f"- rows missing from candidate ({len(t_only):,})", -missing),
            (f"+ rows only in candidate ({len(c_only):,})", extra),
            (f"+/- value differences on matched keys ({len(matched):,})", matched_diff),
            ("= candidate", c_total),
            ("unexplained residual", residual),
        ]
        for label, amount in bridge_rows:
            out(f"  {label:<45}{money(amount):>18}")
        if residual:
            out("  ^ the residual must be zero — if it is not, the comparison itself is wrong")

        diffs = [(k, t_sums[k][col], c_sums[k][col]) for k in matched
                 if not close(t_sums[k][col], c_sums[k][col], abs_tol, rel_tol)]
        within = len(matched) - len(diffs)
        out(f"\n=== L5  row-level: {col} " + "=" * max(4, 51 - len(col)))
        out(f"matched keys equal within tolerance   {within:,}")
        out(f"matched keys differing                {len(diffs):,}"
            f"   carrying {money(sum((c - t for _, t, c in diffs), Decimal(0)))}")
        if diffs:
            worst_abs = sorted(diffs, key=lambda d: -abs(d[2] - d[1]))[: args.sample]
            out("  largest absolute differences:")
            for k, t, c in worst_abs:
                out(f"    {'|'.join(k):<28} truth {money(t):>14}  cand {money(c):>14}  diff {money(c - t):>14}")
            rel = [(k, t, c) for k, t, c in diffs if t != 0]
            if rel:
                out("  largest relative differences:")
                for k, t, c in sorted(rel, key=lambda d: -abs((d[2] - d[1]) / d[1]))[: args.sample]:
                    out(f"    {'|'.join(k):<28} truth {money(t):>14}  cand {money(c):>14}  "
                        f"{(c - t) / t * 100:+.2f}%")
            for note in pattern_scan(diffs, abs_tol):
                out(f"  pattern: {note}")
                findings.append(f"{col}: {note}")
            findings.append(f"{col}: {len(diffs):,} matched keys differ, net {money(sum((c - t for _, t, c in diffs), Decimal(0)))}")

        report["columns"][col] = {
            "truth_total": str(t_total), "candidate_total": str(c_total), "difference": str(gap),
            "bridge": {"missing_rows": str(-missing), "extra_rows": str(extra),
                       "matched_value_differences": str(matched_diff), "residual": str(residual)},
            "matched_within_tolerance": within, "matched_differing": len(diffs),
            "patterns": pattern_scan(diffs, abs_tol),
        }

    out("\n=== verdict " + "=" * 59)
    if not findings:
        out("no structural or value differences found at this tolerance.")
        out("before believing it: confirm the two inputs are different files, that the")
        out("tolerance is not masking (re-run with --abs-tol 0), and perturb one row to")
        out("prove this check can fail.")
    else:
        for f in findings:
            out(f"  - {f}")
        out("\nnext: take each of these to the hypothesis catalogue, size the cause, and")
        out("check the sized causes sum to the difference above.")
    report["findings"] = findings

    if args.json:
        args.json.write_text(json.dumps(report, indent=2), encoding="utf-8")
        out(f"\nJSON report written to {args.json}")
    return 1 if findings else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:  # piping into head/less
        sys.stderr.close()
        raise SystemExit(0)
