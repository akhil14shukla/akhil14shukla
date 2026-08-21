# More than two files: periods, vintages, and lookups across files

Read this when the comparison involves a folder rather than a pair — monthly
exports, daily snapshots, a period re-issued several times, or a fact table that
only makes sense joined to two other files. The layered method does not change;
what changes is that you must first establish *which file is which*, and that
every extra file adds a join that can fan out and a vintage that can restate.

## Name the shape of the set before comparing anything

| Shape | What the files are | The question that matters |
|---|---|---|
| **Timeline** | One period each, populations barely overlap | Is the series continuous, and does each period's total move for a reason? |
| **Partitions** | One logical dataset split by region, entity, or chunk | Does the union have the right grain, with no gap and no overlap? |
| **Vintages** | The same period exported repeatedly | What was restated between vintages, and which vintage is the truth? |
| **Chained lookups** | Facts plus dimensions, rates, mappings | Does each join match exactly one row, and is it point-in-time correct? |
| **Event vs snapshot** | A log of changes vs a state at a moment | Does replaying the events reproduce the snapshot? |

The overlap between consecutive files tells you which you have: near-zero is a
timeline, near-total is vintages, partial overlap is the dangerous middle —
double counting on the union.

`scripts/track_across_files.py` does this diagnosis, the inventory, the sequence
check, per-period totals with step changes, key churn, and restatement
detection in one pass:

```bash
python scripts/track_across_files.py --files "exports/*.csv" --key order_id --value amount
python scripts/track_across_files.py --files "vintages/*.xlsx" --key order_id --lookup ORD-00417
```

## Inventory and sequence integrity

Before any total is believed:

- **One row per file**: path, period, row count, distinct keys, totals, and how
  the period was determined (from the filename or from a column). A file named
  `2026-01` containing February rows is common enough to check every time.
- **Gaps** — a missing period is not an empty period. An absent file and a file
  with zero rows mean different things and both are findings.
- **Duplicate periods** — two files for one period is a re-export (use the later
  one, and say so) or double counting (fix the union).
- **Overlapping windows** — exports with a re-stated tail (`last 7 days` run
  daily) share rows. Dedupe on key **plus** period before totalling, and check
  which vintage's values you kept.
- **Row counts per period** — a period at 3× or 0.2× its neighbours is the
  finding, before you look at a single value.

## Vintages, restatements, and moving answers

If a row can change after it is first exported, "the total for January" is a
function of *when you asked*. So:

- **Fix a vintage** and state it: "ledger as at 2026-02-15 for January". Without
  it, re-running tomorrow silently produces a different reconciliation.
- **Archive the truth you compared against.** You cannot investigate a
  discrepancy from last month against a table that has since been recomputed.
- **Distinguish legitimate restatement from a bug** by whether it follows a
  rule: late-arriving events restate the most recent periods only; a refund
  restates the original order's period; a bug restates arbitrary old rows.
- **Watch for round-trips** — a value that changed and changed back is invisible
  if you only compare the first and last file, which is why the check runs over
  consecutive pairs.

## Point-in-time joins (the "current value" leak)

The most damaging multi-file error is joining a historical fact to a dimension's
*current* row: last year's orders priced at today's price, a closed account's
transactions attributed to its new owner. The symptom is that history changes
when you re-run.

Join on the version that was in force at the event's time:

```sql
SELECT f.order_id, f.amount, d.price
FROM   fact_orders f
JOIN   dim_price d
  ON   d.sku = f.sku
 AND   f.ordered_at >= d.valid_from
 AND   f.ordered_at <  d.valid_to      -- half-open, so instants belong to exactly one row
```

Before trusting a versioned dimension, check it: exactly one row valid at any
instant per key (no overlapping ranges), no gaps between `valid_to` and the next
`valid_from`, and an open-ended final row. A type-1 dimension that overwrites in
place has no history at all — old periods cannot be reproduced from it, and that
limitation belongs in the report rather than in a footnote.

## Chaining lookups across files

Each hop multiplies risk. At every join, in order:

1. State the expected cardinality — `1:1`, `m:1`, never `m:m` by accident.
2. Prove the right-hand key is unique **before** joining, not after.
3. Compare the row count before and after. A join that changes the row count has
   changed every total downstream, and is the single most common cause of
   confidently wrong numbers.
4. Count the rows that failed to match and decide what they mean; an inner join
   silently deletes them, which turns a coverage finding into missing money.

Prefer joining to an aggregate over aggregating after a join: aggregate the
detail file to the fact's grain first, then join `m:1`.

## Comparing the series, not just the pair

Once each period reconciles, the timeline itself is evidence:

- Tabulate the **difference per period**, not the two levels. Two near-identical
  lines hide what a difference series makes obvious.
- **Step change** — dates the cause to a deploy, a rule change, or a new source.
- **Linear drift** — an accumulating error: a rounding rule, a missing accrual,
  a filter that captures a growing share of rows.
- **Spike then return** — a one-off load or an outage, not a logic difference.
- **Noise around zero** — rounding or timing; size it and stop.

Then test any cause **out of sample**: a hypothesis derived from January must
also explain February. If it does not, it describes January rather than
explaining anything.

Normalise before comparing periods: 28 vs 31 days, the number of business days,
holidays, and a partial current period. A "12% drop in February" is usually the
calendar.

## Roll-forward: the strongest multi-period check

Where the data has opening and closing states, reconcile the movement rather
than the levels:

    opening balance + additions − removals ± adjustments = closing balance

Run it per period and per entity. It catches what period-by-period totals
cannot: a row that moved between categories, a deletion dressed up as an update,
and any transaction that exists in the closing state without a movement to
explain it. The residual of a roll-forward is a much sharper number than the
difference between two totals, because there is nowhere for a compensating error
to hide.
