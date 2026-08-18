# SQL

The rules that separate code a maintainer trusts from code that merely runs in SQL, plus the footguns that cause real production bugs.

- **Never build a query by string concatenation with user input.** Parameterised
  queries only — this is SQL injection, still the most exploited class of web
  vulnerability.
- Name every column you select. `SELECT *` breaks when a column is added,
  transfers data you do not use, and hides which index would help.
- Every query that can return many rows has a `LIMIT` and a deterministic
  `ORDER BY`. Pagination without a stable sort silently returns duplicates and
  skips rows.
- Index the columns you filter, join, and sort on — and know that a leading
  wildcard `LIKE '%x'` and a function applied to a column (`WHERE lower(email)`)
  both prevent index use unless you add a matching expression index.
- Read the `EXPLAIN ANALYZE` output before declaring a query fast. A sequential
  scan on a 200-row table in dev is a sequential scan on 20M rows in production.
- Keep transactions short and never hold one open across a network call to
  another service; that is how connection pools exhaust.
- Migrations are forward-only, reviewed, and tested against production-sized
  data. Adding a column with a default, adding an index, or changing a type can
  each lock a large table — check the semantics for your engine and version, and
  use the concurrent/online variant.
- Put schema constraints in the schema: `NOT NULL`, foreign keys, `CHECK`,
  unique indexes. Application-level validation alone always drifts.
