# Running the comparison: loading, SQL, pandas, spreadsheets

Read this when actually executing the checks. The recipes are grouped by tool;
read the section for the tool you are in. Loading is first because most wrong
answers are already wrong by the time the data is in memory.

## Loading without corrupting the data

The default settings of every CSV and spreadsheet reader are optimised for
convenience, not fidelity. Override them.

- **Read keys as text.** An order ID read as a number loses leading zeros, and
  IDs past 15 digits lose precision silently — two different IDs can become the
  same float. `dtype=str` on key columns, always.
- **Read money as `Decimal` or integer minor units** where exactness matters
  (`converters={"amount": Decimal}` in pandas, `NUMERIC` in SQL). Binary floats
  cannot represent 0.10.
- **Do not let the reader guess dates.** Parse explicitly with a known format;
  `01/02/2026` is two different days depending on locale.
- **Watch the null list.** Readers coerce `NA`, `N/A`, `NULL`, `-`, `nan` and
  even `None` to null by default, which turns a real category value into a
  missing one. Set `keep_default_na=False, na_values=[""]` when the distinction
  matters.
- **Excel specifics** — the displayed value is not the stored value (formatting
  rounds); dates are serial numbers from 1899-12-30; `.xlsx` stores at most 15
  significant digits; a sheet may have hidden rows, an applied filter, merged
  cells above the header, and a total row at the bottom. Read the sheet by name,
  not by index, and print the first and last three rows before trusting it.
- **CSV specifics** — BOM on the first header, embedded newlines inside quotes,
  a delimiter that appears in the data, inconsistent quoting, trailing blank
  line. Compare the parsed row count with `wc -l` and reconcile any difference.
- **After loading, always print** row count, column dtypes, null counts, and
  `head`/`tail`. Every subsequent number depends on this being right.

## Bundled script

`scripts/reconcile.py` runs layers 1–5 with exact decimal arithmetic and needs
no third-party packages. It reads CSV/TSV and basic `.xlsx`, and prints schema,
key uniqueness, coverage, totals, the bridge, worst offenders, and a pattern
scan over the differing rows.

```bash
python scripts/reconcile.py --truth ledger.csv --candidate export.xlsx \
    --key order_id --value amount --value qty \
    --abs-tol 0.005 --normalize-keys --json out.json
```

Use it for the first pass, then move to SQL or pandas for the parts it points
at. `--normalize-keys` reports how many rows matched only after normalising —
treat that count as a finding, not a fix.

## SQL

```sql
-- L2: is the key actually unique?
SELECT order_id, COUNT(*) c FROM export GROUP BY order_id HAVING COUNT(*) > 1
ORDER BY c DESC LIMIT 20;

-- L3: coverage, both directions, in one pass
SELECT CASE WHEN t.order_id IS NULL THEN 'candidate_only'
            WHEN c.order_id IS NULL THEN 'truth_only'
            ELSE 'matched' END AS side,
       COUNT(*), SUM(COALESCE(t.amount, c.amount))
FROM truth t FULL OUTER JOIN candidate c USING (order_id)
GROUP BY 1;

-- L4: totals sliced, so compensating errors cannot hide
SELECT DATE_TRUNC('month', t.created_at) AS m,
       SUM(t.amount) AS truth, SUM(c.amount) AS cand,
       SUM(c.amount) - SUM(t.amount) AS diff
FROM truth t FULL OUTER JOIN candidate c USING (order_id)
GROUP BY 1 ORDER BY 1;

-- L5: differing rows, worst first
SELECT t.order_id, t.amount, c.amount, c.amount - t.amount AS diff
FROM truth t JOIN candidate c USING (order_id)
WHERE ABS(c.amount - t.amount) > 0.005
ORDER BY ABS(c.amount - t.amount) DESC LIMIT 50;
```

Notes: `EXCEPT`/`EXCEPT ALL` compares whole rows and is the fastest way to ask
"is anything different at all" — `EXCEPT ALL` also catches duplicates, which
`EXCEPT` swallows. Beware `NULL = NULL` being unknown: join on
`t.k IS NOT DISTINCT FROM c.k` when keys can be null, and remember `WHERE
diff > x` silently drops null-valued rows.

## pandas

```python
import pandas as pd
from decimal import Decimal

kw = dict(dtype={"order_id": str}, keep_default_na=False, na_values=[""])
t = pd.read_csv("ledger.csv", **kw)
c = pd.read_csv("export.csv", **kw)

# L2 — uniqueness before any join
assert t.order_id.is_unique, t.order_id.value_counts().head()

# L3 — coverage in both directions
m = t.merge(c, on="order_id", how="outer", indicator=True,
            suffixes=("_t", "_c"), validate="one_to_one")
print(m._merge.value_counts())

# L4/L5 — totals, then row-level with an explicit tolerance
print(t.amount.sum(), c.amount.sum(), c.amount.sum() - t.amount.sum())
both = m[m._merge == "both"].copy()
both["diff"] = both.amount_c - both.amount_t
bad = both[both["diff"].abs() > 0.005]
print(len(bad), bad["diff"].sum())
print(bad.reindex(bad["diff"].abs().sort_values(ascending=False).index).head(20))

# Pattern scan over the differing rows
print((bad.amount_c / bad.amount_t).describe())   # a constant ratio is a units/sign bug
print(bad["diff"].describe())                     # a constant offset is a fixed adjustment
```

`validate="one_to_one"` is the highest-value argument here: it raises instead of
silently fanning out, which is the failure that produces confidently wrong
totals. Use `indicator=True` on every reconciliation merge. For a quick
whole-frame check, `df1.compare(df2)` works only when both frames are identically
indexed and shaped — align them first, or it reports differences that are really
misalignment.

## Spreadsheets

When the deliverable must stay in a sheet, keep the comparison in formulas so a
reviewer can click any cell and see where the number came from.

- `=XLOOKUP(key, truth_keys, truth_amount, "MISSING")` for coverage and value
  lookup in one step; count `"MISSING"` for the truth-only side and repeat in
  the other direction.
- `=SUMIF`/`=SUMIFS` for slice totals; `=COUNTIFS` for the row counts that must
  accompany them.
- Compare with `=ROUND(a-b, 2)<>0` rather than `=a<>b`; a displayed 100.00 can
  be 99.999999.
- `=TRIM(CLEAN(UPPER(key)))` for key normalisation, in a helper column, never
  overwriting the original.
- Freeze the source data on its own sheet, untouched, and do all working on a
  separate one — an analysis that edits its own inputs cannot be re-run.
