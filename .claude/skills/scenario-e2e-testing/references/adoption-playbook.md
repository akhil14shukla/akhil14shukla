# Adoption playbook: from zero to a PR gate

Read this when introducing scenario E2E testing into a specific application.
It is the step-by-step plan: what to look for in the codebase, what to build in
what order, what to ask the humans, and how to know each phase is done. Each
phase ends in a mergeable PR.

## Contents

- Phase 0 — Discovery (no code changes)
- Phase 1 — Harness skeleton and one green scenario
- Phase 2 — Determinism hooks in the app
- Phase 3 — The Dynamics fake
- Phase 4 — The scenario catalogue
- Phase 5 — CI gate
- Phase 6 — Prove it catches bugs, then keep it alive
- Questions only humans can answer
- Final report template

## Phase 0 — Discovery (no code changes)

Answer each question from the code, and write the answers into
`e2e/README.md` as the first artefact. Search before reading
(the `codebase-recon` approach): grep for the term, read the matching range.

| Find | How to search | Why |
|---|---|---|
| Stack, entry point, how the app starts | `Dockerfile`, `docker-compose*.yml`, `Program.cs`, `main.py`, `package.json` scripts, `pom.xml` | Compose service and start command |
| Health endpoint | `grep -rniE "health|ready|liveness"` in routes | Runner readiness |
| API routes for receipts, matching, validation, posting | grep the router/controller registrations; OpenAPI spec if present (`openapi.json`, Swagger setup) | The `when` steps |
| Migration tool and command | `alembic.ini`, `Migrations/` + EF, `db/migration/V*.sql` (Flyway), `liquibase`, `prisma/schema.prisma`, `knexfile` | `migrate_command`, `keep_tables` |
| Does the app migrate itself on startup? | grep `Migrate()`, `flyway.migrate`, `upgrade head` in startup | Order of `prepare` vs app start |
| Tables involved in AR | migrations / ORM models for receipts, invoices, allocations, customers, journals, statuses, audit | `snapshot.tables`, fixtures |
| Dynamics client: base URL config key, auth (MSAL / Azure.Identity / raw HTTP), paths called | `grep -rniE "dynamics|operations\.dynamics|businesscentral|crm\.dynamics|/data/|odata|login\.microsoftonline|oauth2"` | Which product (`dynamics-mock.md` §1), stub paths, config keys to override |
| Is the token authority configurable? | look where the token URL/authority is built | Blocker if hard-coded — Phase 2 fix |
| Retry/timeout policy | grep `retry|backoff|polly|tenacity|resilience4j|Retry-After|timeout` | Scenario expectations for 429/503/timeouts |
| Clock usage | `grep -rnE "DateTime\.(Now|UtcNow|Today)|datetime\.(now|utcnow)|date\.today|new Date\(|Date\.now|LocalDate\.now|Instant\.now|time\.Now\(" src/` and SQL `now()`/`CURRENT_DATE` | Phase 2 clock hook |
| Background jobs / schedulers / queues | grep `Hangfire|Quartz|BackgroundService|IHostedService|celery|apscheduler|cron|@Scheduled|bull|Service Bus|consumer` | Phase 2 job hook or `wait_for` |
| Caches | grep `MemoryCache|IMemoryCache|lru_cache|cache` near token / settings / FX | Phase 2 cache reset hook |
| Existing tests and CI | `.github/workflows`, `azure-pipelines.yml`, test dirs | Where the gate goes; conventions |
| Existing manual test cases, bug tickets, incident notes | ask; check `docs/`, wiki links in README | Phase 4 source material |

Exit criteria: `e2e/README.md` lists the stack, the routes, the tables, the
Dynamics product + paths + config keys, every clock/job/cache location, and the
open questions for humans.

## Phase 1 — Harness skeleton and one green scenario

1. Create `e2e/` per `architecture.md` §9. Copy:
   - `scripts/scenario_runner.py` → `e2e/scenario_runner.py`
   - `assets/templates/docker-compose.e2e.yml` → `e2e/docker-compose.e2e.yml`; adapt
     every `ADAPT` line (Postgres major = production's, app build context, env
     var names from Phase 0).
   - `assets/example/e2e.config.yaml` → `e2e/e2e.config.yaml`; set
     `migrate_command`, `keep_tables`, `snapshot.tables`.
   - `assets/wiremock-d365/` → `e2e/wiremock/` (even if unused until Phase 3, the
     token default lets the app boot).
2. Write `e2e/seed/base_reference_data.sql`: the minimum reference rows the app
   needs to start and serve one request (legal entities, currencies, settings).
3. Write one scenario for the simplest read-or-write flow that does not touch
   Dynamics (e.g. create a receipt → assert the row).
4. Add `out/` to `.gitignore` and a `make e2e` (or equivalent) target.

Exit criteria: `make e2e` from a clean clone starts the stack, prepares the DB,
and passes that scenario twice in a row.

## Phase 2 — Determinism hooks in the app

Smallest possible app changes, each behind `E2E_TEST_HOOKS=1`, with a startup
guard that refuses the flag in production (`architecture.md` §8):

1. **Clock**: introduce one clock abstraction (if none exists) and replace the
   direct calls found in Phase 0 on the AR paths. Add `PUT /__test/clock`.
2. **Jobs**: `POST /__test/jobs/{name}/run` for each background job on the AR
   path (auto-match sweep, posting queue, retry sweeper, status sync); disable
   the scheduler when the flag is set.
3. **Caches**: `POST /__test/reset-caches` if Phase 0 found caches on the path;
   call it from the runner by chaining it in `app.clock` or as a first step.
4. **Configurable endpoints**: Dynamics base URL and Entra authority from config.
5. **E2E-friendly resilience settings**: retry back-off cap and HTTP timeout
   from config (same retry counts as production).

Exit criteria: a scenario with `clock:` asserts a date the app derived from it;
a scenario that needs a background job triggers it via the hook; production
config is unchanged.

## Phase 3 — The Dynamics fake

1. Rename paths and fields in `e2e/wiremock/mappings/` to what the app's client
   actually calls (Phase 0). Verify against the environment's `$metadata` if
   reachable.
2. Ideally record one real happy-path exchange from a sandbox
   (`dynamics-mock.md` §7), scrub it, and use its response bodies.
3. Collect real error bodies from production logs for the D365 errors seen in
   the last year; make one stub per distinct error.
4. Write AR-POST-001 (happy path) asserting full payloads and order.

Exit criteria: happy-path posting scenario passes with `erp_unmatched: none`
(no unstubbed calls), and its `erp_requests` pin company, account, amount,
currency, date, and invoice reference.

## Phase 4 — The scenario catalogue

1. Build the list: `ar-case-catalog.md` §9 priority order, plus every manual
   test case and incident from Phase 0. Write it as a table in `e2e/README.md`:
   id, title, source (ticket/incident/manual case), status.
2. For each case, before writing YAML: **state the expected outcome in one
   sentence**. Cases where you cannot are questions for the finance owner —
   collect them, ask in one batch, do not guess.
3. Write scenarios in batches of 5–10 per PR, grouped by stage. Each batch PR
   lists which catalogue rows it covers.
4. When a scenario fails against current code, decide: is the expectation
   wrong, or is the app? If the app, that is a found bug — file it, mark the
   scenario `skip: "BUG-123"` *only* if it cannot be fixed in the same PR, and
   report it.

Exit criteria: priorities 1–4 of the catalogue covered (typically 30–50
scenarios), every Dynamics error from production logs has a scenario, and the
open-questions list is answered or explicitly parked by a named owner.

## Phase 5 — CI gate

1. Copy `assets/templates/github-workflow-e2e.yml` (or the Azure DevOps one),
   adapt paths, run it on the PR that adds it.
2. Measure wall-clock time; add shards or build caching to stay under 10 min.
3. Ask a repository admin to make the check required (you usually cannot do
   this yourself — say so explicitly in the report).
4. Add to the PR template: "Behaviour change? Scenario added/updated: ___".

Exit criteria: check runs on every PR, is required on the default branch, and
uploads JUnit + diagnostics on failure.

## Phase 6 — Prove it catches bugs, then keep it alive

**Mutation round** — the only evidence the suite works. Introduce, one at a
time on a throwaway branch, realistic bugs and confirm a scenario fails for
each:

| Mutation | Should be caught by |
|---|---|
| Drop the credit-hold check | AR-VAL-001 |
| Retry only on 503, not 429 | AR-POST-003 |
| Reverse allocation order | AR-MATCH-006-style scenario |
| Round half-even instead of half-up (or vice versa) | AR-RND-003 |
| Send `DebitAmount` instead of `CreditAmount` | AR-POST-001 payload assertion |
| Hard-code company instead of entity mapping | AR-POST-011 |
| Retry a 400 | AR-POST-004 (call count) |
| Mark posted when the response lacks a voucher | AR-POST-013 |
| Remove the already-posted guard | AR-VAL-003 |

Every mutation that survives is a missing scenario: write it, and re-run the
mutation. (When this was done on the bundled example app, reversing the
allocation order survived the original 16 scenarios; AR-MATCH-006 was added
because of it.)

**Keeping it alive**:

- Behaviour-changing PRs update expectations in the same PR.
- Every production incident on the AR path gets an AR-REG scenario before its
  fix is merged.
- Review skipped scenarios monthly; the count trends to zero.
- Bump pinned Postgres/WireMock/action versions deliberately, one per PR.

## Questions only humans can answer

Ask these in one batch, with the scenario each one blocks:

1. Which Dynamics product and version, and which environment can be used for
   the nightly contract job (if any)?
2. Matching policy: tolerances (absolute/%), write-off accounts, allocation
   order, subset matching on/off, third-party payments, credit-note netting.
3. Posting policy: posting date (receipt date vs today), period-closed
   behaviour, approval thresholds, batch sizes.
4. Unknown-outcome policy: what should happen after a timeout during posting?
5. Copies of real D365 error messages from logs (or access to the logs).
6. The manual regression checklist the team runs today, and recent incidents.

## Final report template

```
E2E scenario suite — status
- Stack: <postgres version>, WireMock <version>, app image from PR
- Scenarios: <N> (<n> matching, <n> validation, <n> posting, <n> regression); <k> skipped (tickets: ...)
- Runtime on CI: <m> min across <s> shards
- Mutation round: <x>/<y> mutations caught; survivors and the scenarios added for them
- Bugs found while writing scenarios: <list with tickets>
- Not covered yet: <catalogue rows> — reason
- Needs a human: make the check required; answer policy questions <list>
```
