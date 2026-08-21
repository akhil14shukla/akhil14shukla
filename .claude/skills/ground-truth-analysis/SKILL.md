---
name: ground-truth-analysis
description: Compare a sheet, export, report, or model output against a ground truth and explain every difference — set the comparison contract, reconcile in layers, test each hypothesis, attack your own answer, and hand a human a bridge whose sized causes sum exactly to the gap. Use whenever two sets of numbers are being checked against each other: "do these match", "reconcile this", "validate this export against the source of truth", "why don't the totals agree", "QA these figures", "check my numbers", "compare this spreadsheet to the database", "predicted vs actual", "the migrated data looks wrong", or when a discrepancy has already been found and needs a cause. Also use to turn a recurring comparison into a reusable skill.
---

# Ground-truth analysis

A number that differs is not a finding. **The finding is the mechanism that
produced the difference**, stated precisely enough to predict the next
difference. "Revenue is off by 42,318" is a symptom; "orders after
the 23:00 cut are missing because the export cuts on local time, not UTC — 187
orders, 42,318" is a finding.

The second trap is subtler: **most reconciliations that reach a wrong answer are
wrong about the comparison, not about the numbers.** Two correct datasets at
different grains or as-of times disagree loudly and truthfully.

## First write the comparison contract

Before any diffing. Where an answer is unknown, write the assumption into the
report rather than silently picking one.

- **Grain** — one row is one *what*? (order? order-line? order-day?) The most
  common cause of a fake discrepancy is two different grains.
- **Keys** — which columns identify a row on each side, and are they unique?
- **Row context** — of the remaining columns, which describe the row, which
  measure it, which record how it was loaded. They turn a difference into an
  explanation, so carry them through the whole comparison.
- **Scope** — filters, date range, entity set, statuses each side includes.
- **As-of** — when each side was captured, in which timezone, and whether
  either still moves (restatements, late rows, soft deletes).
- **Units and conventions** — currency and FX date, scale (units/thousands),
  sign convention (are refunds negative?), rounding and precision.
- **Tolerance and materiality** — what counts as equal, and what is big enough
  to act on. Different numbers; state both.
- **Authority** — why the ground truth is the reference, and what would make it
  the wrong one.

## Reconcile in layers, and stop at the first failure

Each layer's answer is meaningless until the one below it holds.

| L | Layer | Fails when |
|---|---|---|
| 0 | Provenance — the query, file, and run you think it is | You are diffing a stale export |
| 1 | Shape and schema — counts, types, encoding, nulls | A column parsed as text, a blank row |
| 2 | Keys and grain — uniqueness, nulls, case/whitespace/zeros | Duplicates fan out a join, inflating a total |
| 3 | Coverage — which keys are on both sides, which on one | Rows are missing, not wrong |
| 4 | Totals — overall, then per slice | An error hides inside a matching total |
| 5 | Row-level values on matched keys, within tolerance | Compensating errors |
| 6 | Distribution and behaviour — shape, outliers, drift | Values are plausible but shifted |

Comparing values at layer 5 while layer 2 is broken produces thousands of fake
differences and hides the real one.

**A folder rather than a pair** — periods, vintages, a chain of lookups — still
runs the layers per pair, but first establish which file is which: each extra
file adds a join that can fan out and a vintage that can restate the answer
under you.

## One hypothesis, one falsifiable test, one number

Rank candidate causes by prior, boring first: scope filter, timing, duplicates,
units, join fan-out, rounding, null handling, sign. Exotic causes are last
because they are rare, not because they are uninteresting.

Let the data nominate: split the gap across each descriptive, status and
lineage column; a cause that sits in one region, status or batch names itself.
State each hypothesis as a prediction that can fail — *"if it is the timezone
cut, the difference is exactly the rows between 18:00 and 23:00 UTC: ~187 rows,
~42,300"* — then run the test that could refute it. A hypothesis that survives
because it was never given a chance to fail is not evidence. Expect several
causes: keep going until the residual is zero or you can name what is left.

## The bridge is the deliverable

Ground-truth total → each cause with its amount and row count → candidate total,
where the explained amounts sum **exactly** to the gap. An unexplained residual
gets its own line, never rounded away or absorbed into another cause.

## Attack your own answer before someone else does

Diff both directions. Prove the harness works: truth against itself is zero,
one perturbed row caught. Treat a perfect match as a hypothesis — a file
compared with itself, a masking tolerance, a join that dropped rows. Look for
compensating errors that net to zero at the total but not per slice. And keep
open that the ground truth is the reference, not the truth: if the evidence says
it is wrong, say so, with proof.

## Done check

Every material difference has a named mechanism, a quantity, and a test that
could have refuted it; the bridge closes to zero or names its residual; the
assumptions are written down; and a reader who was not in the analysis can act
on the report without asking what a column means.

## Read the reference that matches your task

| If you are… | Read |
|---|---|
| Running the checks — what each layer tests | `references/check-battery.md` |
| Deciding which columns matter, or a difference has no explanation | `references/column-semantics.md` |
| Comparing many files — periods, vintages, as-of joins | `references/multi-file-and-time.md` |
| Explaining a difference you have found | `references/hypotheses.md` |
| Setting tolerance, comparing distributions, or sampling | `references/statistical-checks.md` |
| Trying to break your own conclusion | `references/adversarial-review.md` |
| Writing it up — bridge tables, exhibits, severity | `references/reporting.md` |
| Loading files, or writing the comparison in SQL or pandas | `references/tooling.md` |
| Asked to make this repeatable as a skill | `references/codify-into-skill.md` + `assets/recon-skill-template.md` |

## Bundled scripts

Stdlib only; shared loading in `scripts/tabular.py`:

```bash
python scripts/profile_columns.py --file export.csv
python scripts/reconcile.py --truth ledger.csv --candidate export.xlsx \
    --key order_id --value amount --by region
python scripts/track_across_files.py --files "exports/*.csv" --key order_id
```
