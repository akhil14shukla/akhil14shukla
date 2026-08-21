# What every column is for, and why the ignored ones explain the gap

Read this before choosing which columns to compare, when a difference has no
explanation yet, or when a file has forty columns and the comparison uses three.
The measure columns tell you *how big* the difference is. Every other column is
what tells you *what it is* — and a reconciliation that carries only keys and
amounts has thrown away its own evidence before starting.

Profile first, so this is fact rather than assumption:

```bash
python scripts/profile_columns.py --file export.csv --key order_id
python scripts/profile_columns.py --file jan.csv --file feb.csv   # same name, same meaning?
```

## The six roles

Classify every column. The role decides what the column can do for you.

| Role | Looks like | Why it matters here |
|---|---|---|
| **Identity** | Unique, non-null, id-shaped | Defines the grain and the join. Wrong here and nothing downstream is real. |
| **Temporal** | Dates, timestamps, valid-from/to | Decides scope and vintage. Several per row, and only one was used by the filter. |
| **Dimension / flag** | 2–50 distinct values: region, status, type, currency | The attribution surface. A gap that sits in one value is a mechanism. |
| **Measure** | Numeric, many distinct values | What you compare — but only after you know its additivity, sign and units. |
| **Derived** | Computed from other columns | Free internal consistency check: recompute it on each side separately. |
| **Metadata / lineage** | batch id, load time, source system, file name, version, is_deleted | The fastest explainers in the file. Group differing rows by these *first*. |

Free text (notes, comments, description) is a seventh, uncomparable but often
decisive: read the notes on the ten worst rows before theorising. Somebody has
frequently written down exactly what happened.

## Temporal columns: which time is this?

A row commonly carries `created_at`, `updated_at`, `ordered_at`, `posted_date`,
`effective_date`, `loaded_at`. They differ by hours to months, and:

- The filter that built each side used exactly **one** of them; the two sides
  often used different ones. That alone produces a clean, systematic
  "missing rows" finding.
- `updated_at` changes when nothing economically changed, so it is a poor
  as-of filter and an excellent restatement detector.
- `loaded_at` describes the pipeline, not the business — never scope a business
  question by it, but always group discrepancies by it.

## Measures: additivity is a property, not an assumption

| Kind | Examples | Rule |
|---|---|---|
| **Additive** | amount, quantity, count, fee | Sums across every dimension including time |
| **Semi-additive** | balance, headcount, stock level, position | Sums across entities, **never across time** — take the closing value |
| **Non-additive** | rate, price, percentage, ratio, score, average | Never sum. Recompute from `sum(numerator)/sum(denominator)` |

Summing a semi-additive or non-additive column is the most common way a
reconciliation produces two numbers that are both wrong and disagree. If a
"total" of a rate column exists on either side, that is the finding.

Also settle per measure: sign convention (are refunds negative, or positive in a
separate column?), units embedded in the name (`amount_cents`, `qty_thousands`),
and currency — a column summing three currencies has no meaning at all, and its
matching totals are a coincidence.

## Four checks the descriptive columns make possible

**1. Attribute the gap across every dimension.** For each dimension and metadata
column, sum each value's contribution to the difference, then look at the
concentration. Scattered evenly means keep looking; ~100% in one value names the
mechanism:

    by region:   APAC  -4,121.34   100% of movement, 20 keys (1 of 3 regions)
    by batch:    B1    -1,164.72    28% of movement,  5 keys

That first line is a hypothesis handed to you. `scripts/reconcile.py` does this
automatically for low-cardinality columns, and for any column named with `--by`.

**2. Check the descriptive columns themselves on matched keys.** A row can carry
the right number attached to the wrong thing: same order, different region,
different status, different customer. Totals still tie, every slice is wrong,
and a value-only comparison sees nothing.

**3. Recompute the derived columns on each side independently.** If
`gross = qty × unit_price` holds in the truth and fails in the candidate, you
have identified the wrong side without needing to compare the two at all — and
you have found the broken step in the pipeline, not just its symptom.

**4. Test the functional dependencies.** If `sku → category` holds on one side
and breaks on the other, the mapping table changed or was joined as-of the wrong
time. Dependencies also warn you about **correlated dimensions**: when
`region → currency` holds, "the difference is in EMEA" and "the difference is in
EUR" are one cause, not two, and reporting both double counts your own
explanation.

## Cross-file column traps

- **Same name, different meaning.** `amount` net of tax in one system, gross in
  another; `date` as the event in one file and the load in another. Compare the
  profiles (role, cardinality, null rate, range) side by side before mapping the
  columns to each other.
- **Meaning changed at a date.** A column redefined mid-history reconciles
  before the change and not after; the break in the difference series dates it.
- **A column that is present but always empty on one side**, so every comparison
  involving it silently passes.
- **Different null conventions** — `""`, `NULL`, `0`, `"N/A"`, `-`. Decide
  whether null equals null for your purpose, and report how many rows depend on
  that decision.
- **Extra columns on one side only.** They are not noise: they usually record
  the transformation that explains the difference.

## The deliverable: a column dictionary

For anything that recurs, write it once — name, role, meaning in business terms,
source system, additivity, null convention, units, and an example value. It is
the artefact that stops the next person re-deriving all of the above, and it
belongs in the generated skill (`references/codify-into-skill.md`, and the
contract table in `assets/recon-skill-template.md`).
