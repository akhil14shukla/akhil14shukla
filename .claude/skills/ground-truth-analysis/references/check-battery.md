# The check battery, layer by layer

Read this while running a comparison. Work down the layers and stop at the
first one that fails — a failure at any layer invalidates every layer above it,
so fixing it usually deletes most of the differences you were about to
investigate.

Each check below names what it catches. Run the cheap structural ones even when
the totals already match: a matching total with a broken join is the most
expensive kind of false confidence.

## L0 — Provenance

Before anything is loaded, establish what is actually in your hands. Nearly
every "impossible" discrepancy is a stale or mislabelled input.

- **What produced each side?** Query text, script version, report parameters,
  export button. Record it; you will need it in the write-up.
- **When was each captured?** File mtime, export timestamp, `MAX(updated_at)`.
  If the two captures straddle any writes, some difference is expected and you
  must quantify it rather than explain it away.
- **Is the ground truth authoritative for this question?** A warehouse table is
  ground truth for reporting and *not* for "what the app showed the user".
  A vendor statement is authoritative for what they will pay, not for what was
  earned. Name what would make it the wrong reference.
- **Is either side still moving?** Restatements, late-arriving events, soft
  deletes, and reversals mean re-running tomorrow gives a different answer.
- **Has anyone edited the file?** A spreadsheet that has been opened, sorted,
  and saved can be re-typed, re-rounded, or re-ordered. Check for manual
  overrides, hidden rows, filters left applied, and formulas replaced by values.

## L1 — Shape and schema

- Row count, column count, and column names on each side; which columns exist
  only on one side.
- **Header handling** — multi-row headers, title rows above the header, merged
  cells, trailing total rows, blank separator rows, footnotes at the bottom.
  A trailing "Total" row silently doubles every total you compute.
- **Type inference** — a numeric column read as text (thousands separators,
  currency symbols, parentheses for negatives, trailing spaces, `1,234` vs
  `1.234`), an ID read as a number (leading zeros lost, `1e5` notation,
  precision lost past 15 digits), a date read as a string or an Excel serial.
- **Encoding and whitespace** — UTF-8 vs Latin-1 mojibake, BOM on the first
  header, non-breaking spaces, smart quotes, CRLF, trailing spaces in keys.
- **Null semantics** — `NULL` vs `""` vs `0` vs `"N/A"` vs `-` vs missing row.
  They are four different facts and every one of them is sometimes right.
  Decide explicitly whether a null value equals a null value for your purpose.
- **Precision** — floats displayed rounded but stored long, fixed-point vs
  binary float, values stored in cents vs units.

## L2 — Keys and grain

- Are the key columns present, non-null, and unique on each side? Count
  duplicates and the maximum multiplicity, not just "yes/no".
- **Grain mismatch** — one side per order, the other per order-line or per
  order-day. Symptom: candidate rows are an integer-ish multiple of truth rows,
  or a `GROUP BY key HAVING COUNT(*) > 1` returns a stable small number.
- **Join fan-out** — if you join before you have proved uniqueness, a duplicate
  on one side multiplies values on the other. Always compare row counts before
  and after a join; a join that grows the row count has changed the arithmetic.
- **Key normalisation** — case, whitespace, leading zeros, hyphens in UUIDs,
  `int` vs `str`, unicode normalisation, IDs recycled across systems. Compare a
  hash of the normalised key, and report how many rows only match after
  normalising (that is itself a finding).
- **Composite keys** — a key that is unique only with the date included, where
  one side's date is a timestamp and the other's is a day.

## L3 — Coverage

Set arithmetic on the normalised keys, before any value is compared:

- `matched`, `truth_only`, `candidate_only` — counts and the value they carry.
- **Are the one-sided rows systematic?** Sort them by date, entity, region,
  status, source system, and by key range. Missing rows clustered at the end of
  a date range is a cut-off; clustered in one region is a filter; scattered
  uniformly is a sampling, dedup, or partial-load problem.
- **Duplicate coverage** — keys present twice on one side only.
- Coverage in *both* directions. "All my rows are in the truth" says nothing
  about the rows you dropped.

## L4 — Totals and subtotals

- Overall total per numeric column, both sides, plus the difference and the
  percentage.
- **Then break it down** — by month, entity, category, status, source. A
  matching grand total with wildly differing slices is compensating errors, and
  is more dangerous than an obvious mismatch. Slice on at least one dimension
  even when the total matches.
- **Count-based totals too** — sum, count, count-distinct, min, max, and null
  count. A sum can match while the count does not (a zero-valued row missing),
  and count-distinct catches duplication that sum hides.
- **Scale and sign scan** — if `candidate/truth` is ~1000, ~0.01, ~1.1, or
  ~-1 for the whole column, you have a units, percent, tax, or sign-convention
  difference, not a data problem.

## L5 — Row-level values on matched keys

- Compare with an explicit tolerance (see `references/statistical-checks.md`);
  never compare floats with `==`, and never let a tolerance be "whatever makes
  it pass".
- Report **counts and amounts** together: 12 rows differing by 4.1M is a
  different problem from 40,000 rows differing by 4.1M.
- Rank offenders by both **absolute** and **relative** difference. Absolute
  finds the material ones; relative finds the systematic ones hiding in small
  rows.
- **Scan the differences for a pattern** before treating them as individual
  errors: a constant offset, a constant ratio, differences that are all under
  half a unit (rounding), all one-sided (a floor or a filter), all on one
  category, all in one date range, or exactly the value of some other column.
- Compare **non-numeric fields too** where they matter — status, category, flag.
  A row can have the right amount attached to the wrong thing.

## L6 — Distribution and behaviour

Reached when values are individually plausible but you do not trust them, or
when there are no shared keys at all (two independently produced populations).

- Compare quantiles (min, p1, p25, median, p75, p99, max), mean, standard
  deviation, and null rate per column, on each side.
- Compare category frequencies and the top-N by value.
- Look for a shifted or clipped distribution: values capped at a maximum,
  a spike at zero, negatives that should not exist, an unexpected mode.
- Digit and unit checks: a spike at round numbers suggests manual entry; a
  Benford deviation in naturally occurring financial data suggests
  transformation or fabrication (weak evidence alone — treat as a prompt, not a
  verdict).
- Time-series drift: plot or tabulate the difference by period. A step change
  dates the cause to a deploy; a linear divergence suggests an accumulating
  error; noise around zero suggests rounding or timing rather than logic.
