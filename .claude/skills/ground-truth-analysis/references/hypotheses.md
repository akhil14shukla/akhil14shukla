# Hypothesis catalogue: what causes differences, and how to falsify each

Read this when a difference exists and you need a cause. Work down the table —
it is ordered by how often each cause is the real one, and the cheap tests are
at the top. Do not skip to the interesting explanations; "the logic is wrong" is
the *last* hypothesis, not the first, and reaching for it early is how a
timezone bug gets shipped as a rewrite.

## How to state a hypothesis so it can fail

A usable hypothesis names a mechanism, predicts a quantity, and says what would
refute it:

> **Mechanism:** the export filters on local date while the truth uses UTC.
> **Prediction:** every missing row has `created_at` between 18:00 and 23:59
> UTC on the boundary day; ~180 rows; ~42k; no missing rows elsewhere.
> **Refuted if:** missing rows appear on non-boundary days, or the boundary
> window contains rows that *are* present.

Then run the test that could refute it. Confirming that some missing rows are
in the window proves nothing — thousands of rows are in that window. **Test the
prediction that would break, not the one that would hold.**

Quantify every accepted hypothesis in the same units as the headline gap, so
the causes can be summed into the bridge. A cause you cannot size is a
suspicion, not a finding.

## The catalogue

| # | Hypothesis | Signature | Test that could refute it |
|---|---|---|---|
| 1 | **Different scope/filter** — one side excludes cancelled, internal, test, or zero rows | Differences are entirely one-sided; missing rows share a status/flag value | Group the one-sided rows by every categorical column; a filter shows as one value carrying ~100% |
| 2 | **Different as-of time** — captures taken at different moments | Missing rows cluster at the end of the date range; re-export closes part of the gap | Restrict both sides to `<= min(cutoff)` and re-run; the gap should collapse |
| 3 | **Timezone / boundary** — local vs UTC, `[start, end)` vs `[start, end]` | Difference lives entirely in the first or last N hours of the range | Shift the boundary by the offset; if it is the cause, the gap goes to zero, not just down |
| 4 | **Grain mismatch** — order vs order-line vs daily rollup | Row-count ratio is near-integer; keys duplicate on exactly one side | Aggregate the finer side to the coarser grain and re-compare; totals should match exactly |
| 5 | **Join fan-out / duplicates** — a dup on one side multiplies the other | Total is an odd multiple; row count grew after the join | Count rows before/after the join; dedupe the key and re-total |
| 6 | **Units or scale** — thousands vs units, cents vs dollars, %, bps | Ratio is a clean power of ten (or 100 / 10,000) across the whole column | Divide and check the residual is *exactly* zero, not merely small |
| 7 | **Sign convention** — refunds, credits, contra accounts, debit/credit | Ratio ≈ −1 on a subset; the gap is exactly twice the subset's absolute value | Flip the sign on that subset only; a convention explains all of it or none |
| 8 | **Rounding and precision** — round-then-sum vs sum-then-round, float drift, half-up vs banker's | Every difference is under half a unit; total gap grows with row count | Compare at full precision; the row-level differences should vanish |
| 9 | **Currency / FX** — different rate, rate date, or conversion point | Ratio is constant per currency, not overall; local-currency rows match | Split by currency: non-converted currencies should reconcile exactly |
| 10 | **Null and default handling** — null vs 0 vs missing; `COALESCE` on one side | Differences concentrate on rows null on one side; count matches, sum does not | Compare only rows non-null on both sides; the gap should disappear |
| 11 | **Deduplication rule** — different tie-break for "the current row" | Same key, both values legitimate, differ in an `updated_at`-like column | Apply the truth's tie-break to the candidate; matched values should agree |
| 12 | **Late-arriving / restated data** — the truth was recomputed after the export | Differences on old rows that were correct in an earlier run | Compare against an archived version of the truth from the export's date |
| 13 | **Type coercion on load** — IDs as floats, leading zeros lost, dates as serials | Unmatched keys become matched after normalising; ID-like keys end in `.0` | Re-load with explicit dtypes; count how many keys only match after normalisation |
| 14 | **Encoding / whitespace in keys** | Near-identical keys on both sides that fail to join | Join on a normalised key and count newly matched rows |
| 15 | **Wrong denominator / weighting** — an average of averages, unweighted mean | Only ratio metrics differ; the underlying sums agree | Recompute the ratio as `sum(num)/sum(den)`; if it matches, the metric was the bug |
| 16 | **Double counting** — a row counted in two categories, or a rollup added to its own children | Slice totals sum to more than the grand total | Check that the parts sum to the whole on each side independently |
| 17 | **Sampling or partial load** — truncated file, row limit, failed partition | Missing rows are uniform and the count is suspiciously round (10,000; 65,536; 1,048,576) | Compare against the source count; look for a limit at a power of two or ten |
| 18 | **Business-logic difference** — genuinely different definitions of the metric | Survives every check above; differences track a rule (thresholds, tiers, proration) | Recompute one side under the other's stated rule and see if it reproduces |
| 19 | **Upstream defect** — one side is genuinely wrong | Only after 1–18 are eliminated; a mechanism in the producing code | Reproduce from raw inputs; point at the line or the query |
| 20 | **The ground truth is wrong** | The candidate is internally consistent and matches a third source | Bring in an independent third source; do not assert this without one |

## Working several hypotheses at once

Real gaps usually have three or four causes stacked. Keep them separate:

1. Take the largest unexplained chunk first; explain it; **remove those rows or
   that adjustment from the population** and re-measure the residual.
2. Repeat on the new residual. Each pass should shrink it monotonically. If a
   fix makes the residual *grow*, your causes overlap — you have counted one
   effect twice, or the fix broke something that was previously cancelling out.
3. Stop when the residual is zero, or small enough to be immaterial *and* you
   can say what kind of thing it is ("128 rows, all sub-cent rounding").

Never let a residual be absorbed into a cause you have already sized. Two
hypotheses that each "explain about half" and were never sized separately
usually mean neither is right.

## Confounders that fake a cause

- **Simpson's paradox** — the difference reverses per segment. Always test a
  hypothesis at the segment level, not just on the total.
- **Compensating errors** — two real causes that net to zero at the grand total.
  They only appear in per-slice or per-row comparisons.
- **Correlated causes** — cancelled orders are also mostly recent orders, so a
  status filter and a timing cut look identical. Separate them with a
  cross-tab: hold one constant and vary the other.
- **The fix that hides the symptom** — normalising keys, coercing types, or
  widening tolerance makes differences disappear without explaining them.
  Every normalisation is a finding to report, with a count.
