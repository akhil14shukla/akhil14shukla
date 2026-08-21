# Writing it up so a human can act on it

Read this when the analysis is done. The reader is usually not the person who
ran the checks — a finance lead, an engineer who owns the pipeline, an auditor.
They need to reach a decision without reproducing your work, and to be able to
reproduce it if they choose.

## Structure

1. **Answer first, in one sentence with the number.** "The export understates
   revenue by 42,318 (0.31%); 96% of it is a timezone cut in the export job, and
   the rest is rounding."
2. **The bridge** — the whole gap, decomposed, summing exactly.
3. **One section per cause** — mechanism, evidence, size, and what to do.
4. **What was checked and found clean.** This is what makes the report
   trustworthy: it shows the space you searched, not just where you found
   something.
5. **Limits and open items** — what you could not check, the residual, the
   assumptions you had to make, what would change the answer.
6. **Reproduction** — the exact files, queries, commit, and command.

Lead with the answer even when the news is "they match": a reader who has to
hunt for the conclusion will invent one.

## The bridge table

The single most useful exhibit in this kind of work. Every line is a mechanism
with a quantity; the lines sum to the gap; the last line is what you cannot
explain.

| Step | Rows | Amount | Running total |
|---|---|---|---|
| Ground truth (ledger, 2026-07) | 128,455 | 13,904,221.50 | 13,904,221.50 |
| − Orders after the 23:00 local cut | −187 | −42,180.00 | 13,862,041.50 |
| − Cancelled orders excluded by export | −41 | −9,905.25 | 13,852,136.25 |
| + Test-account orders included in export | +12 | +1,204.00 | 13,853,340.25 |
| ± Round-then-sum on line discounts | 3,904 | −22.31 | 13,853,317.94 |
| **= Export total** | **128,239** | **13,853,317.94** | — |
| Unexplained residual | 0 | 0.00 | — |

Rules that keep it honest: every line has a sign, a row count, and an amount;
the residual is always shown even when zero; and no line is labelled
"other/timing" — if you cannot name it, it belongs in the residual.

## Making each cause credible

For each cause, four things, in this order:

- **Mechanism** — the specific behaviour, in one sentence, naming where it
  happens: "`export_orders.py` filters on `DATE(created_at)` in server local
  time; the warehouse aggregates in UTC."
- **Evidence** — the smallest exhibit that makes it obvious. Usually a table of
  the affected rows by some dimension, where one row of the table carries
  nearly all of the difference. Include two or three real example rows with
  their keys, so a reader can look them up.
- **Size** — rows and amount, matching the bridge line exactly.
- **So what** — the consequence and the fix, separately: "understates every
  month-end by roughly this much; fix is to cut on UTC, and the last six
  month-ends need restating."

State confidence explicitly where it is not total: "confirmed — re-running the
export with a UTC cut reproduces the ledger figure exactly" is different from
"consistent with the evidence; not reproduced".

## Numbers on the page

- Same precision as the source, and say the units in the header (`Amount (USD)`,
  `Qty (thousands)`). Never mix scales in one column.
- Give both absolute and relative sizes; each alone misleads.
- Always pair a total with a row count — 42,318 across 187 rows and across
  187,000 rows are different findings.
- Round for display only, never before summing, and say when you have rounded.
- If you show a chart, show the difference over time rather than the two series
  — a step change dates the cause, and two near-identical lines show nothing.

## Language

- Name mechanisms, not blame: "the export cuts on local time", not "the data
  team used the wrong timezone".
- Say "differs from" for facts and reserve "wrong" for what you have proved.
- Expand every internal term the first time. If the reader has to know what
  `dim_orders_v2` is, name it as "the orders table the dashboard reads".
- No hedging adverbs on numbers you have verified, and no confident voice on
  numbers you have not. "Approximately" is a claim about precision — use it only
  where you mean it.

## Severity

Sort findings by materiality against the decision, not by how interesting they
were to find:

| Severity | Test | Example |
|---|---|---|
| Blocking | Changes a decision, a payment, or a filed figure | Revenue misstated above the reporting threshold |
| Material | Above materiality but does not change the decision | A regional total off by 0.4% |
| Systematic-but-small | Immaterial per row, one-sided, will grow | Rounding always in the same direction |
| Immaterial | Within tolerance, two-sided, bounded | Float noise across 3,904 rows |

A systematic-but-small finding is worth reporting even when the amount is
trivial, because the mechanism is real and the population usually grows.

## Reproduction appendix

Enough for someone else to get your exact numbers: source file names with
timestamps and row counts, the query text or script path with its commit, the
tolerance and materiality used, the command you ran, and where the outputs are.
An analysis nobody can re-run is an opinion.
