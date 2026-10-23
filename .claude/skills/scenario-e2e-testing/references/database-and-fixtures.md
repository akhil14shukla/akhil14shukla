# Database and fixtures

Read this when building the e2e database, deciding what goes in base seed
versus fixtures versus a scenario, turning a production incident into a
scenario, or keeping fixtures alive through schema changes.

## Contents

1. Four layers of data
2. Building the schema: use the app's own migrations
3. Base seed: reference data only
4. Fixtures: shared row graphs
5. Writing rows that survive schema change
6. Harvesting a production case into a scenario
7. Anonymising
8. Time, money, and other traps
9. Making Postgres fast in CI

## 1. Four layers of data

| Layer | Where | Changes | Contains |
|---|---|---|---|
| Schema | the app's migrations (`migrate_command`) | with every migration | tables, constraints, functions, enum values |
| Base seed | `e2e/seed/*.sql` (`base_seed`) | rarely | legal entities/companies, currencies, payment methods, posting profiles, tolerance settings, a few ordinary customers |
| Fixtures | `e2e/fixtures/*.sql` | when a shared shape changes | row graphs several scenarios reuse: "customer with two open invoices", "receipt matched to one invoice" |
| Scenario rows | `given.rows` inline | per scenario | the rows the rule under test is about |

A value a scenario's outcome depends on belongs in the scenario, not in base
seed. If changing a base-seed tolerance from 5.00 to 2.00 would flip a scenario
from pass to fail, that scenario must set the tolerance itself (via `rows` or a
mid-scenario `sql` step), or the dependency is invisible to the next reader.

## 2. Building the schema: use the app's own migrations

`prepare` creates the database and runs `migrate_command` with the DSN in the
environment variable `url_env` (default `DATABASE_URL`):

| Stack | `migrate_command` |
|---|---|
| Python / Alembic | `alembic upgrade head` |
| Django | `python manage.py migrate --noinput` |
| .NET / EF Core | `dotnet ef database update --connection "$DATABASE_URL"` (or a migration bundle: `./efbundle --connection "$DATABASE_URL"`) |
| Java / Flyway | `flyway -url=jdbc:postgresql://localhost:5432/ar_e2e -user=postgres -password=postgres migrate` |
| Java / Liquibase | `liquibase --url=... update` |
| Node / Prisma | `npx prisma migrate deploy` |
| Node / Knex, TypeORM | `npx knex migrate:latest` / `npx typeorm migration:run -d dist/data-source.js` |
| Go / golang-migrate | `migrate -path db/migrations -database "$DATABASE_URL" up` |
| Raw SQL | `schema_files: [db/schema.sql]` instead of a command |

`migrate_command` runs on the machine running the runner. If the migration tool
lives only in the app image, run it there:
`docker compose -f e2e/docker-compose.e2e.yml run --rm -e DATABASE_URL=postgresql://postgres:postgres@postgres:5432/ar_e2e app <command>`
(note the compose-network hostname `postgres`). If the app migrates itself on
startup, leave `migrate_command` unset, start the app after `prepare`, and add
the migration history table to `keep_tables` so truncation leaves it alone.

Using the real migrations is non-negotiable: it is the only way scenarios catch
a migration that broke a constraint, a default, or a trigger.

## 3. Base seed: reference data only

Write it as plain `INSERT` statements with natural keys, readable in review:

```sql
INSERT INTO legal_entities (code, name, msd_data_area_id, base_currency) VALUES
    ('US01', 'Contoso US', 'usmf', 'USD'),
    ('GB01', 'Contoso UK', 'gbsi', 'GBP');
INSERT INTO currencies (code, decimals) VALUES ('USD', 2), ('GBP', 2), ('JPY', 0), ('KWD', 3);
INSERT INTO match_settings (legal_entity, abs_tolerance, pct_tolerance) VALUES ('US01', 5.00, 0.0);
```

Include currencies with 0 and 3 decimals even if production has none yet: they
are where rounding bugs live.

## 4. Fixtures: shared row graphs

Name fixtures by the situation, not the test: `two_open_invoices_c001.sql`,
`receipt_matched_to_inv1001.sql`, `customer_on_hold_c900.sql`. A fixture must be
safe to combine with others (distinct keys), so give each fixture its own
key range: customers `C0xx` ordinary, `C9xx` special status; invoices
`INV-1xxx` per fixture block.

Create a fixture when a third scenario needs the same graph; before that,
inline rows are clearer.

## 5. Writing rows that survive schema change

- **List columns explicitly**; never rely on column order
  (`INSERT INTO t VALUES (...)` breaks on every added column).
- **Omit columns that have sensible defaults** so a new nullable or defaulted
  column needs no fixture edits.
- **When a migration adds a NOT NULL column without a default**, the run fails
  loudly with the table and column — that is the desired outcome. Fix fixtures
  in the same PR as the migration.
- **When a business rule changes on purpose**, the scenarios that encoded the
  old rule fail. Update their expectations in the same PR, and the reviewer sees
  the rule change as a diff of expected values — that review is a feature.

## 6. Harvesting a production case into a scenario

Every incident, every "finance found this in UAT", every manual test case
becomes a scenario. The goal is the **minimal row graph** that reproduces it,
not a dump.

1. **Identify the root row** (the receipt, the payment batch).
2. **Walk its foreign keys** to collect what it touches. List the outgoing FKs
   of a table with:

   ```sql
   SELECT conrelid::regclass AS child, a.attname AS column,
          confrelid::regclass AS parent, af.attname AS parent_column
   FROM pg_constraint c
   JOIN pg_attribute a  ON a.attrelid = c.conrelid  AND a.attnum = ANY (c.conkey)
   JOIN pg_attribute af ON af.attrelid = c.confrelid AND af.attnum = ANY (c.confkey)
   WHERE c.contype = 'f' AND c.conrelid = 'receipts'::regclass;
   ```

   Swap `conrelid` for `confrelid` in the `WHERE` to list incoming FKs (child
   rows such as allocations).
3. **Extract the rows as YAML-ready JSON**, one query per table, on a read
   replica:

   ```sql
   SELECT json_agg(t) FROM (
     SELECT invoice_no, customer_no, currency, amount, open_amount, due_date, status
     FROM invoices WHERE customer_no = 'C123' AND status <> 'paid') t;
   ```

   Select only the columns that matter, which is also the first anonymisation
   pass.
4. **Anonymise** (§7) and **rekey** into the fixture key ranges.
5. **Shift dates** so they sit relative to the scenario `clock`, keeping the
   same distances (days past due, period boundaries).
6. **State the correct outcome** with the person who reported it — not what the
   code did. Write it in `then`.
7. **Run it against the current code and watch it fail for the reported
   reason**, then fix the code. A regression scenario that never failed proves
   nothing.

For a larger extraction (dozens of tables), `pg_dump --data-only
--column-inserts --table=... ` on a scratch copy restricted to the root's rows
is faster than hand queries; still cut it down before committing.

## 7. Anonymising

Scenarios live in the repository; production data must not. Before commit:

- Replace customer names, addresses, emails, bank accounts, IBANs, remittance
  free-text, and payer names with obviously fake values (`Contoso`, `Fabrikam`,
  `Litware`, `C001`).
- Keep **the shape** that caused the bug: the typo in the reference, the
  trailing space, the Unicode dash, the 35-character truncation, the amount.
- Amounts are rarely sensitive on their own; keep them when the arithmetic is
  the point (rounding, tolerance), otherwise scale them.
- For bulk work, tooling exists: Greenmask (logical dump with deterministic
  transformers and subsetting) and the PostgreSQL Anonymizer extension
  (masking rules declared in the database). Use them when you need large
  anonymised datasets; hand-masking is fine for a handful of rows.

## 8. Time, money, and other traps

- **Money is `numeric(p,s)`, never float.** Scenarios compare numbers as
  decimals, so `1000` matches `1000.00`. If the app sends floats to Dynamics
  (common in JSON), assert the value it sends: a `CreditAmount` of
  `0.30000000000000004` is a bug worth a scenario.
- **Rounding**: half-up vs half-even (banker's) differ at `.005`. Write one
  scenario per currency decimals class.
- **Dates vs timestamps**: posting date is a *date* in the legal entity's
  calendar. A receipt at `2026-03-31T23:30:00-05:00` is March in New York and
  April in UTC. Scenario: clock at that instant, assert the posting period.
- **Column defaults using `now()`** are not controlled by the app's clock; put
  them in `snapshot.ignore_columns` and assert with `{{iso_datetime}}` if at all.
- **Sequences** are restarted per scenario; explicit ids in `rows` do not
  advance them (§ scenario-format: do not mix).
- **Triggers and functions** run during seeding. If a trigger writes an audit
  row on insert, your seed creates audit rows too; assert accordingly or seed
  the audit table's expected state.
- **Enum types**: a new value in a Postgres enum needs a migration; scenarios
  that use it fail with a clear error until the migration exists.

## 9. Making Postgres fast in CI

- Run on `tmpfs` with `fsync=off`, `synchronous_commit=off`,
  `full_page_writes=off` (the compose template does). Safe because the data is
  discarded; never in production.
- Keep base seed small (hundreds of rows, not millions).
- `truncate` reset cost grows with table count, not row count; a 300-table
  schema truncates in well under a second.
- Profile before optimising: the runner prints seconds per scenario. If most
  time is in the app (slow startup per request, N+1 queries), that is a finding
  about the app.
