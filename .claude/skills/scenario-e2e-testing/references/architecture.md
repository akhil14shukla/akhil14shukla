# Architecture and decisions

Read this when designing the harness for a new application, choosing between
reset strategies, deciding how the app talks to the fakes, or making the system
deterministic (clock, ids, background jobs). Skip it if the harness already
exists and you are only adding scenarios — read `scenario-format.md` instead.

## Contents

1. What this testing style is, and is not
2. The moving parts
3. One scenario's lifecycle
4. Decision 1 — black-box runner or in-process tests
5. Decision 2 — how the database is reset
6. Decision 3 — where the ERP is faked
7. Decision 4 — determinism: clock, ids, ordering, background work
8. Test hooks the application must expose
9. Repository layout
10. Anti-patterns

## 1. What this testing style is, and is not

**Known-state scenario testing** (also called golden-database or
state-transition E2E testing): every test starts from a database state you wrote
down by hand, drives the application only through its public API, and asserts
the exact end state — HTTP responses, rows in Postgres, and calls made to
external systems. Because you authored the starting state, you can state the
correct answer before running anything. That makes the test an executable
statement of a business rule: *"a receipt quoting INV-1001 for the full amount
pays INV-1001, leaves INV-1002 open, and sends nothing to Dynamics."*

It is the layer that replaces manual regression testing. It is **not**:

- A replacement for unit tests. Matching heuristics with dozens of numeric
  edge cases (rounding, tolerance boundaries) are cheaper as unit tests; keep
  one or two scenarios per rule to prove the wiring, and unit-test the
  arithmetic exhaustively.
- A test against real Dynamics. PR builds must be hermetic: no network, no
  shared sandbox, no credentials. A separate, optional nightly contract job
  checks the fake still behaves like the real API (`dynamics-mock.md` §8).
- A load test. Scenarios use a handful of rows each.

Target: the whole suite runs on every PR in **under 10 minutes** wall-clock,
including build. At ~0.2–0.5 s per scenario that is 500+ scenarios on two shards.

## 2. The moving parts

```
                       ┌─────────────────────────────── CI job / dev machine ─┐
 scenario YAML files ─►│ scenario_runner.py                                   │
                       │   reset DB ─┐   stub ERP ─┐   HTTP calls ─┐  assert   │
                       └─────────────┼─────────────┼───────────────┼──────────┘
                                     ▼             ▼               ▼
                              ┌────────────┐ ┌────────────┐ ┌───────────────┐
                              │ Postgres   │ │ WireMock   │ │ Application   │
                              │ (prod major│ │ = Entra ID │ │ under test    │
                              │  version)  │ │ + Dynamics │ │ E2E_TEST_HOOKS│
                              └─────▲──────┘ └─────▲──────┘ └──────┬────────┘
                                    │              │   token, OData │
                                    └──── SQL ─────┼────────────────┘
                                                   └── app's real HTTP client
```

- **Postgres**: the same major version as production, migrated by the app's
  real migration tool. Never SQLite, H2, or an in-memory substitute — the edge
  cases you are guarding against include numeric precision, locking, and
  constraint behaviour, which only real Postgres reproduces.
- **WireMock**: one process impersonating both the Entra ID token endpoint and
  the Dynamics 365 API. The app reaches it through its *real* HTTP client, so
  serialisation, auth headers, retry and error parsing are all exercised.
- **The application**: started once, configured by environment variables to
  use the e2e database and WireMock, with test hooks enabled.
- **The runner** (`scripts/scenario_runner.py`): resets state, seeds, stubs,
  calls the API, and compares. It knows nothing about the app's language.

## 3. One scenario's lifecycle

1. **Reset the database** to "migrated + base reference data" (§5).
2. **Seed** the scenario's `given.sql` files then `given.rows`, in order.
3. **Reset WireMock** (`POST /__admin/reset`): default mappings reload from
   disk, the request journal empties, stateful scenarios return to `Started`.
4. **Stub** the scenario's `given.erp_stubs` on top of the defaults.
5. **Set the clock** through the app's test hook, if the scenario has `clock`.
6. **Snapshot** the tables listed in `then.db_unchanged`.
7. **Run `when` steps**: HTTP requests (with response checks and `save`),
   `wait_for` polls, mid-scenario SQL, mid-scenario stubs.
8. **Assert `then`**: table contents, unchanged tables, ERP calls (count,
   payload, order), and no ERP call that no stub covered.
9. Optionally **capture** the actual end state to draft expectations.

Each scenario is independent: it can run alone, in any order, on any shard.

## 4. Decision 1 — black-box runner or in-process tests

| | Black-box runner (default) | In-process (pytest / xUnit / JUnit / Jest) |
|---|---|---|
| App runs as | its real container/binary | inside the test process |
| Language coupling | none: same runner for any stack | one per stack |
| What it proves | the shipped artefact works, config included | the code works |
| Parallelism | shards (one stack per CI job) | per-test DB clone, many workers |
| Debugging | logs + journal artefacts | breakpoints |
| Scenario format | YAML, reviewable by finance/QA | code |

**Default to the black-box runner.** It tests what you deploy, the scenarios are
readable by the people who know the business rules, and an LLM can adopt it
without learning the app's test framework. Choose in-process only when the
suite outgrows sharding (thousands of scenarios) or the team insists on
debugger-first workflows; the scenario YAML can then be loaded by a test
framework fixture with the same semantics (`runner-and-ci.md` §6).

## 5. Decision 2 — how the database is reset

| Strategy | How | Cost per scenario | Use when |
|---|---|---|---|
| `truncate` (default) | `TRUNCATE` every table except `keep_tables`, `RESTART IDENTITY`, restart all sequences, re-run `base_seed` | ~20–100 ms | The app keeps a connection pool open (almost always) |
| `template` | `DROP DATABASE … WITH (FORCE)` then `CREATE DATABASE … TEMPLATE <tpl>` | ~50–300 ms for small schemas | Base seed is large, or schema has objects TRUNCATE does not reset (materialised views, unlogged caches) |

`template` mode terminates the app's connections every scenario. The app's pool
must transparently replace dead connections (HikariCP, Npgsql, SQLAlchemy with
`pool_pre_ping=True`, node-postgres all can; verify yours). If the first request
of each scenario fails with "terminating connection due to administrator
command", enable pre-ping/validation or use `truncate`.

Facts that matter for `template`: Postgres cannot copy a template while anything
is connected to it, so the runner marks it `ALLOW_CONNECTIONS false`; from
Postgres 15 the default `STRATEGY = WAL_LOG` is the fast choice for small
databases, while `FILE_COPY` forces two checkpoints but wins for multi-GB
templates.

Never "roll back the transaction after each test" in black-box mode: the app
commits in its own connections, so the test cannot own the transaction.

## 6. Decision 3 — where the ERP is faked

Fake at the **network boundary**, not inside the app:

| Option | Verdict |
|---|---|
| WireMock (HTTP fake) at the Dynamics base URL and the Entra authority URL | **Default.** Exercises the real client, auth, retry, timeouts, error parsing. Language-agnostic. Journal lets you assert exactly what was sent. |
| Mock the app's `DynamicsClient` interface in code | Only for unit tests. Hides the bugs that matter most: wrong payload shape, missing header, retry not honouring `Retry-After`, error body not parsed. |
| Real Dynamics sandbox | Never on PR builds: shared mutable state, throttling, credentials, flakiness. Use for the nightly contract job only. |

For this to work the app must read **both** URLs from configuration: the D365
base URL *and* the Entra token authority. Hard-coded
`https://login.microsoftonline.com` is the most common blocker — make it a
config value defaulting to the real one.

## 7. Decision 4 — determinism

A scenario that passes 99 times and fails once is worse than none. Remove every
source of variation:

| Source | Fix |
|---|---|
| Wall clock in app code (`now()`, `DateTime.UtcNow`, `new Date()`, `LocalDate.now()`) | Route all reads through one injectable clock; expose `PUT /__test/clock`. Posting dates, period checks, due-date and discount logic all depend on it. |
| `now()` / `CURRENT_TIMESTAMP` in SQL and column defaults | Have the app pass timestamps it read from its clock. Where defaults remain (`created_at`), list the columns in `snapshot.ignore_columns` and assert them with `{{iso_datetime}}`. Shadowing `now()` via `search_path` does not reach `CURRENT_TIMESTAMP` or column defaults. |
| Serial/identity ids | The runner restarts all sequences, so ids are deterministic per scenario; still prefer asserting natural keys (`receipt_no`) and `save` ids from responses. |
| UUIDs, random numbers | Assert with `{{uuid}}` / `{{any}}`, or inject a seeded generator in e2e mode. |
| Row order | Unordered by default; add `order_by` only when order is the rule under test. |
| Time zones, locale | Postgres, app, and runner all on `UTC`; set `TZ=UTC` and `timezone=UTC`. Dates in scenarios are ISO-8601. |
| Background workers, schedulers, queues | Disable the scheduler in e2e mode and expose `POST /__test/jobs/{name}/run` that runs one job synchronously; or, if the worker must run, use `wait_for`. Never `sleep`. |
| Caches (token cache, exchange-rate cache, config cache) | Expose `POST /__test/reset-caches` and call it from `app.clock` or a first step, or keep caches per-request in e2e mode. A cached Entra token silently skips your token-failure scenarios. |
| Exchange rates, holidays, external reference data | Seed them as rows, or stub the provider in WireMock. |
| Retry back-off sleeps | Fakes return `Retry-After: 0`; cap back-off via config in e2e mode so retry scenarios take milliseconds. |

## 8. Test hooks the application must expose

Only with `E2E_TEST_HOOKS=1`, and the app must **refuse to start** if that flag
is set while the environment name is production (fail closed). Register the
routes only when the flag is on, so they do not exist otherwise.

| Hook | Purpose |
|---|---|
| `PUT /__test/clock {"now": "..."}` | Freeze app time for the scenario. |
| `POST /__test/jobs/{name}/run` | Run a background job (posting batch, retry sweeper, status sync) once, synchronously; return what it did. |
| `POST /__test/reset-caches` | Clear in-memory caches (tokens, settings, FX). |
| `GET /health` | Readiness for the runner and compose. |

That is usually the entire list. Resist hooks that reach into business logic;
if a scenario needs state, seed it.

## 9. Repository layout

```
<repo>/
└── e2e/
    ├── e2e.config.yaml           runner configuration
    ├── docker-compose.e2e.yml    postgres + wiremock + app
    ├── scenario_runner.py        copied from this skill (or vendored as a package)
    ├── seed/
    │   └── base_reference_data.sql   legal entities, currencies, customers every scenario shares
    ├── fixtures/                 row graphs several scenarios reuse
    ├── scenarios/
    │   ├── ingestion/  matching/  validation/  posting/  reversal/  regressions/
    ├── wiremock/
    │   ├── mappings/             defaults loaded at boot (token + happy path)
    │   └── stubs/                failure modes scenarios opt into
    └── out/                      gitignored: junit, captures, logs
```

## 10. Anti-patterns

- **A production dump as the base state.** Thousands of rows nobody
  understands; expectations become "whatever it did last time". Harvest the
  *minimal* row graph per case instead (`database-and-fixtures.md` §6).
- **Scenarios that depend on each other** ("run 012 after 011"). Every scenario
  seeds what it needs.
- **Asserting everything.** A `then` that lists every column of every table
  breaks on every harmless change. Assert the columns the rule is about, plus
  `db_unchanged` for tables that must not move.
- **Asserting nothing about Dynamics.** Every scenario that should not call the
  ERP says so: `{url_path_pattern: ".*", count: 0}`.
- **Copying the app's logic into expectations.** Expected values are literals a
  human worked out, never computed by the test.
- **Fixing a red scenario by re-capturing** without understanding the
  difference. `--capture` drafts expectations; a human approves them.
