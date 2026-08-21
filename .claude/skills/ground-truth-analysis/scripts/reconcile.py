#!/usr/bin/env python3
"""Reconcile two tables against each other and print a closing bridge.

The structural layers of a reconciliation — schema, key uniqueness, coverage,
totals, row-level differences — are mechanical, and doing them by hand is where
silent join fan-out and float noise get mistaken for findings. This runs them
in order, in exact decimal arithmetic, and decomposes the total gap into
missing rows, extra rows and value differences so the parts sum to the whole.

It then does what a human forgets to: attributes the gap across the descriptive
columns, so a difference that lives entirely in one region, status or batch is
named rather than hunted for, and checks whether those descriptive columns
themselves agree on the rows whose numbers do.

    python reconcile.py --truth ledger.csv --candidate export.xlsx \
        --key order_id --value amount --abs-tol 0.005

    python reconcile.py --truth a.csv --candidate b.csv \
        --key entity --key period --by region --by status --normalize-keys

Stdlib only, via tabular.py. It answers "what differs", not "why" — take its
output back to the hypothesis catalogue for the cause.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Sequence

from tabular import Row, close, key_of, load, money, normalise_key, numeric_columns, to_decimal

MAX_CONTEXT_CARDINALITY = 50  # above this a column labels rows rather than grouping them


def aggregate(rows: list[Row], keys: Sequence[str], values: Sequence[str],
              context: Sequence[str], normalise: bool):
    """Sum values by key, and remember each key's descriptive columns."""
    sums: dict[tuple[str, ...], dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    counts: Counter[tuple[str, ...]] = Counter()
    ctx: dict[tuple[str, ...], Row] = {}
    unparsed: Counter[str] = Counter()
    null_keys = 0
    for row in rows:
        k = key_of(row, keys, normalise)
        if any(part == "" for part in k):
            null_keys += 1
        counts[k] += 1
        ctx.setdefault(k, {c: str(row.get(c, "")).strip() for c in context})
        for col in values:
            parsed = to_decimal(row.get(col, ""))
            if parsed is None:
                if str(row.get(col, "")).strip():
                    unparsed[col] += 1
            else:
                sums[k][col] += parsed
    return sums, counts, ctx, unparsed, null_keys


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


def attribute(gap_by_key: dict[tuple[str, ...], Decimal], ctx: dict[tuple[str, ...], Row],
              column: str) -> list[tuple[str, Decimal, int]]:
    """Split the gap across the values of one descriptive column, largest first."""
    by_value: dict[str, Decimal] = defaultdict(Decimal)
    rows_by_value: Counter[str] = Counter()
    for k, amount in gap_by_key.items():
        value = ctx.get(k, {}).get(column, "") or "(blank)"
        by_value[value] += amount
        rows_by_value[value] += 1
    return sorted(((v, a, rows_by_value[v]) for v, a in by_value.items()), key=lambda r: -abs(r[1]))


def pick_context(common: Sequence[str], exclude: set[str], ctx: dict[tuple[str, ...], Row]) -> list[str]:
    """Descriptive columns worth slicing by: more than one value, few enough to group."""
    picked = []
    for col in common:
        if col in exclude:
            continue
        distinct = {row.get(col, "") for row in ctx.values()}
        if 2 <= len(distinct) <= MAX_CONTEXT_CARDINALITY:
            picked.append(col)
    return picked


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--truth", required=True, type=Path, help="The reference file")
    p.add_argument("--candidate", required=True, type=Path, help="The file being checked")
    p.add_argument("--key", action="append", default=[], help="Key column (repeat for a composite key)")
    p.add_argument("--value", action="append", default=[], help="Numeric column to compare (default: auto-detect)")
    p.add_argument("--by", action="append", default=[], help="Descriptive column to attribute the gap across "
                                                             "(default: auto-detect low-cardinality columns)")
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
    values = args.value or numeric_columns(common, t_rows, c_rows, exclude=set(keys))
    if not values:
        raise SystemExit("no numeric columns found on both sides; pass --value explicitly")
    absent = [v for v in values if v not in t_cols or v not in c_cols]
    if absent:
        raise SystemExit(f"value column(s) not present on both sides: {', '.join(absent)} "
                         f"(use --map CAND=TRUTH if they are named differently)")
    described = [c for c in common if c not in set(keys) | set(values)]
    context = args.by or described
    absent_by = [c for c in args.by if c not in common]
    if absent_by:
        raise SystemExit(f"--by column(s) not present on both sides: {', '.join(absent_by)}")
    out(f"key: {' + '.join(keys)}    comparing: {', '.join(values)}")
    out(f"describing columns carried for attribution: {', '.join(context) if context else '(none)'}")
    if args.normalize_keys:
        out("keys normalised (case, whitespace, leading zeros, trailing .0)")

    t_sums, t_counts, t_ctx, t_unparsed, t_nullkeys = aggregate(t_rows, keys, values, context, args.normalize_keys)
    c_sums, c_counts, c_ctx, c_unparsed, c_nullkeys = aggregate(c_rows, keys, values, context, args.normalize_keys)
    for side, unparsed in (("truth", t_unparsed), ("candidate", c_unparsed)):
        for col, n in unparsed.items():
            out(f"!  {side}: {n:,} non-empty values in {col!r} did not parse as numbers "
                f"— they are excluded from every total below")

    out("\n=== L2  keys and grain " + "=" * 48)
    findings: list[str] = []
    for side, counts, nulls, rows in (("truth", t_counts, t_nullkeys, t_rows),
                                      ("candidate", c_counts, c_nullkeys, c_rows)):
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

    all_ctx = {**c_ctx, **t_ctx}  # truth wins where a key exists on both sides
    slice_by = pick_context(context, set(), all_ctx) if not args.by else list(args.by)
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

        # Where the gap lives, across each descriptive column.
        gap_by_key: dict[tuple[str, ...], Decimal] = {}
        for k in t_only:
            gap_by_key[k] = -t_sums[k][col]
        for k in c_only:
            gap_by_key[k] = c_sums[k][col]
        for k in matched:
            delta = c_sums[k][col] - t_sums[k][col]
            if delta:
                gap_by_key[k] = delta
        movement = sum((abs(v) for v in gap_by_key.values()), Decimal(0))
        attribution: dict[str, list[dict[str, str]]] = {}
        if len(gap_by_key) >= 3 and slice_by and movement:  # attribution over 1-2 keys is noise
            out(f"\n--- where the {col} gap lives " + "-" * max(4, 41 - len(col)))
            for column in slice_by:
                groups = attribute(gap_by_key, all_ctx, column)
                top_value, top_amount, top_rows = groups[0]
                share = abs(top_amount) / movement * 100
                population = {row.get(column, "") for row in all_ctx.values()}
                out(f"  by {column}:")
                for value, amount, n in groups[: args.sample]:
                    out(f"    {value[:28]:<30} {money(amount):>16}   {abs(amount) / movement * 100:5.1f}% of movement"
                        f"   {n:,} keys")
                if len(groups) > args.sample:
                    out(f"    ... and {len(groups) - args.sample:,} more values")
                if share >= 80 and len(population) > 1:
                    note = (f"{share:.0f}% of the {col} movement is in {column}={top_value!r} "
                            f"({top_rows:,} keys, 1 of {len(population):,} values of {column}) — start there")
                    out(f"    ^ {note}")
                    findings.append(note)
                attribution[column] = [
                    {"value": v, "amount": str(a), "keys": n} for v, a, n in groups[: args.sample]
                ]

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
            findings.append(f"{col}: {len(diffs):,} matched keys differ, net "
                            f"{money(sum((c - t for _, t, c in diffs), Decimal(0)))}")

        report["columns"][col] = {
            "truth_total": str(t_total), "candidate_total": str(c_total), "difference": str(gap),
            "bridge": {"missing_rows": str(-missing), "extra_rows": str(extra),
                       "matched_value_differences": str(matched_diff), "residual": str(residual)},
            "matched_within_tolerance": within, "matched_differing": len(diffs),
            "patterns": pattern_scan(diffs, abs_tol), "attribution": attribution,
        }

    # A row can carry the right number attached to the wrong thing.
    if context and matched:
        out("\n=== L5  descriptive columns on matched keys " + "=" * 27)
        drift: dict[str, int] = {}
        for column in context:
            changed = [k for k in matched
                       if normalise_key(t_ctx[k].get(column, "")) != normalise_key(c_ctx[k].get(column, ""))]
            drift[column] = len(changed)
            flag = "  <- the numbers may be right and attached to the wrong thing" if changed else ""
            out(f"  {column:<28} {len(changed):,} of {len(matched):,} matched keys differ{flag}")
            for k in sorted(changed)[: args.sample]:
                out(f"    {'|'.join(k):<28} truth {t_ctx[k].get(column, '')!r:<20} "
                    f"cand {c_ctx[k].get(column, '')!r}")
            if changed:
                findings.append(f"{column}: differs on {len(changed):,} matched keys "
                                f"— a descriptive column, so totals can still tie while rows are misfiled")
        report["descriptive_drift"] = drift

    out("\n=== verdict " + "=" * 59)
    if not findings:
        out("no structural, value, or descriptive differences found at this tolerance.")
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
