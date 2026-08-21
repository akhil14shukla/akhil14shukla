# Tolerance, distributions, sampling, and whether a match is real

Read this when choosing what counts as equal, when there are no shared keys to
join on, when deciding how much to verify by hand, or when the result came back
suspiciously clean.

## Comparing numbers correctly

**Never compare floats with `==`.** `0.1 + 0.2 != 0.3`, and a sum of a million
rows accumulates error that depends on the order they were added.

Use both an absolute and a relative tolerance, and take whichever is larger:

```python
def close(a, b, abs_tol=0.005, rel_tol=1e-9):
    return abs(a - b) <= max(abs_tol, rel_tol * max(abs(a), abs(b)))
```

- **Absolute** protects small values (a relative test on 0.0001 is meaningless).
  Set it from the domain's smallest meaningful unit — half a cent for money,
  one unit for counts.
- **Relative** protects large ones. `1e-9` catches genuine differences while
  ignoring float noise; `1e-6` is already loose for money.

Prefer avoiding the problem: read money as `Decimal` or integer minor units and
compare exactly. If a comparison needs a tolerance above the domain's smallest
unit, that is a finding to report, not a setting to turn up.

**Rounding rules matter as much as precision.** Round-half-up vs banker's
rounding differs on exactly the values that occur most in prices, and
round-then-sum vs sum-then-round differ by up to `0.5 × n`. Reproduce the
truth's rule; do not average away the difference.

## Tolerance is not materiality

Two separate numbers, and conflating them is how a 4M error gets closed as
"within tolerance":

- **Tolerance** — the point below which a difference is *not a real difference*
  (float noise, a documented rounding rule). Set from arithmetic.
- **Materiality** — the point above which a real difference *is worth acting
  on*. Set from the decision the numbers feed, by the person who owns it.

Report both, and report differences below materiality as a count and a total
rather than dropping them: a thousand immaterial differences all in the same
direction is a systematic bug wearing a disguise.

## When there are no keys to join on

Two independently produced populations (a model's output vs actuals, this
month's file vs last month's, two vendors' extracts) cannot be reconciled row by
row. Compare them as distributions, then explain the shift:

- **Quantiles first** — min, p1, p25, median, p75, p99, max on each side. A
  table of these tells you where the shift is; a single mean does not.
- **Mean, standard deviation, skew, null rate, zero rate, negative count.**
- **Category frequencies** — proportion per category, and the top-N by value.
- **A two-sample test** if you need a number: Kolmogorov–Smirnov for continuous
  data, chi-square for categorical. Treat the statistic as a ranking device,
  not a verdict: at n = 10⁶ every test rejects, so read the effect size (the KS
  statistic itself, or the largest quantile gap) rather than the p-value.
- **Population Stability Index** for monitoring drift between two binned
  distributions: `PSI = Σ (a_i − b_i) · ln(a_i / b_i)` over bins. The
  conventional reading is <0.1 stable, 0.1–0.25 moderate shift, >0.25 material.
  It is a heuristic; it tells you where to look, not what happened.

For predictions vs actuals specifically, report **bias** (mean signed error)
alongside spread (MAE/RMSE). A model that is right on average and wrong every
time is a different problem from one that is consistently 5% high, and only the
signed number distinguishes them.

## Sampling for manual verification

When a full row-level check is impossible, sample deliberately rather than
taking the first 20 rows:

- **Stratify by value** — a plain random sample of a long-tailed financial
  population misses the rows that carry the money. Take all rows above a
  materiality threshold, plus a random sample below it.
- **Cover the edges deliberately** — the largest, the smallest, the zeros, the
  negatives, the nulls, the earliest and latest dates, one row per category.
  Bugs live at boundaries, and a random sample is unlikely to include any.
- **Then take a genuinely random sample** for an unbiased error rate, and say
  the sample size. With zero errors in `n` samples, the upper bound on the true
  error rate is roughly `3/n` (95% confidence) — 30 clean rows means "under
  10%", which is usually not the reassurance people hear.
- Record which rows you checked, so a reviewer can repeat exactly your test.

## When a match is suspicious

A clean result deserves the same scrutiny as a dirty one:

- **Zero differences on the first run** — check you did not load the same file
  twice, join a table to itself, or compare a column to itself. Perturb one row
  in the candidate and confirm the harness reports exactly one difference.
- **Exactly zero rows on one side of the coverage check** — often a filter that
  matched nothing, or a join key that silently coerced to null.
- **A round number of differing rows** (100, 1,000, 65,536) — a limit, not a
  coincidence.
- **A total that matches to the cent while row counts differ** — compensating
  errors, or a total row being included on one side.
- **Every difference in the same direction** — noise is two-sided; a one-sided
  difference is always a mechanism, however small each one is.
- **A tolerance that had to be widened to pass** — record the value that forced
  it and treat it as an open finding.
