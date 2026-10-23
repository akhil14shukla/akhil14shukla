# Adoption playbook: from zero to a PR gate

Read this when introducing scenario E2E testing into any application. It is the
generic, step-by-step plan: what to look for in the codebase, what to build in
what order, what to ask the humans, and how to know each phase is done. Each
phase ends in a mergeable PR.

**Before Phase 0, decide which use-case pack applies — full, partial, or none —
using the table in `use-cases/README.md`, and write the decision at the top of
`e2e/README.md`.** With a full match, read the pack's `playbook.md` alongside
this file; it adds system-specific searches, stubs, cases and questions to each
phase. With no match, this file and the other generic references are the whole
method.

## Contents

- Phase 0 — Discovery (no code changes)
- Phase 1 — Harness skeleton and one green scenario
- Phase 2 — Determinism hooks in the app
- Phase 3 — Fakes for external systems
- Phase 4 — The scenario catalogue
- Phase 5 — CI gate
- Phase 6 — Prove it catches bugs, then keep it alive
- Questions only humans can answer
- Final report template

## Phase 0 — Discovery (no code changes)

Answer each question from the code and write the answers into `e2e/README.md`
as the first artefact. Search before reading (the `codebase-recon` approach):
grep for the term, read only the matching range.

| Find | How to search | Why |
|---|---|---|
| Stack, entry point, how the app starts | `Dockerfile`, `docker-compose*.yml`, `Program.cs`, `main.py`, `package.json` scripts, `pom.xml`, `go.mod` | Compose service and start command |
| Health endpoint | `grep -rniE "health|ready|liveness"` in routes | Runner readiness |
| API routes of the flow under test | router/controller registrations; OpenAPI spec if present | The `when` steps |
| Migration tool and command | `alembic.ini`, EF `Migrations/`, Flyway `V*.sql`, Liquibase, `prisma/schema.prisma`, `knexfile`, golang-migrate dirs | `migrate_command`, `keep_tables` |
| Does the app migrate itself on startup? | grep `Migrate()`, `flyway.migrate`, `upgrade head` in startup code | Order of `prepare` vs app start |
| Tables in the flow | migrations / ORM models for the core entities, their status columns, audit tables | `snapshot.tables`, fixtures, state machines |
| Every external HTTP system | grep base-URL config keys and HTTP client construction: `HttpClient`, `requests`, `httpx`, `axios`, `fetch(`, `RestTemplate`, `WebClient`, `http.Client`; plus `oauth2`, `token`, `client_secret` | Stub inventory (`external-services.md` §1) |
| Are base URL and token authority configurable? | look where each client and its auth are built | Blocker if hard-coded — Phase 2 fix |
| Retry/timeout policy | grep `retry|backoff|Polly|tenacity|resilience4j|Retry-After|timeout` | Expectations for 429/5xx/timeouts |
| Clock usage | `grep -rnE "DateTime\.(Now|UtcNow|Today)|datetime\.(now|utcnow)|date\.today|new Date\(|Date\.now|LocalDate\.now|Instant\.now|time\.Now\(" src/` and SQL `now()`/`CURRENT_DATE` | Phase 2 clock hook |
| Background jobs / schedulers / queues | grep `Hangfire|Quartz|BackgroundService|IHostedService|celery|apscheduler|cron|@Scheduled|bull|consumer|subscriber` | Phase 2 job hook or `wait_for` |
| Caches | grep `MemoryCache|IMemoryCache|lru_cache|cache` near tokens, settings, rates | Phase 2 cache reset hook |
| Existing tests and CI | `.github/workflows`, `azure-pipelines.yml`, `.gitlab-ci.yml`, test dirs | Where the gate goes; conventions |
| Manual test cases, bug tickets, incident notes | ask; check `docs/`, wiki links | Phase 4 source material |

Exit criteria: `e2e/README.md` lists the stack, the routes, the tables, every
external system with its paths and config keys, every clock/job/cache location,
and the open questions for humans.

## Phase 1 — Harness skeleton and one green scenario

1. Create `e2e/` per `architecture.md` §9. Copy from this skill:
   - `scripts/scenario_runner.py` → `e2e/scenario_runner.py`
   - `assets/templates/docker-compose.e2e.yml` → `e2e/docker-compose.e2e.yml`;
     adapt every `ADAPT` line (Postgres major = production's, app build
     context, env var names from Phase 0).
   - `assets/templates/e2e.config.yaml` → `e2e/e2e.config.yaml`; set
     `migrate_command`, `keep_tables`, `snapshot.tables`.
   - An empty `e2e/wiremock/mappings/` plus a token default if the app fetches a
     token at startup (`external-services.md` §5).
2. Write `e2e/seed/base_reference_data.sql`: the minimum reference rows the app
   needs to start and serve one request.
3. Write one scenario for the simplest flow that calls no external system
   (e.g. create an entity → assert the row).
4. Add `e2e/out/` to `.gitignore` and a `make e2e` (or equivalent) target
   (`runner-and-ci.md` §3).

Exit criteria: `make e2e` from a clean clone starts the stack, prepares the DB,
and passes that scenario twice in a row.

## Phase 2 — Determinism hooks in the app

Smallest possible app changes, each behind `E2E_TEST_HOOKS=1`, with a startup
guard that refuses the flag in production (`architecture.md` §8):

1. **Clock**: one clock abstraction (if none exists); replace the direct calls
   found in Phase 0 on the paths under test. Add `PUT /__test/clock`.
2. **Jobs**: `POST /__test/jobs/{name}/run` for each background job on the
   path; disable the scheduler when the flag is set.
3. **Caches**: `POST /__test/reset-caches` if Phase 0 found caches on the path.
4. **Configurable endpoints**: every external base URL and token authority
   from config.
5. **E2E-friendly resilience settings**: back-off cap and HTTP timeout from
   config (same retry counts as production).

Exit criteria: a scenario with `clock:` asserts a date the app derived from it;
a scenario needing a background job triggers it via the hook; production
config is unchanged.

## Phase 3 — Fakes for external systems

For each external system (`external-services.md`):

1. Write default happy-path mappings for every call in the stub inventory,
   requiring the auth header.
2. Ideally record one real exchange from a sandbox (§9 there), scrub it, and use
   its response bodies.
3. Collect real error bodies from production logs; one opt-in stub per distinct
   error, plus the generic failure modes (§6 there).
4. Write the happy-path scenario that calls the system, asserting full payloads
   and call order.

Exit criteria: the happy path passes with `mock_unmatched: none` (no unstubbed
calls), and its `mock_requests` pin every field with business meaning.

## Phase 4 — The scenario catalogue

1. Build the list with `case-catalogue-method.md` (sources, lenses, priority) —
   or, only with a full or domain match, from the pack's catalogue — plus every manual
   test case and incident from Phase 0. Keep it as a table in `e2e/README.md`.
2. For each case, before writing YAML: **state the expected outcome in one
   sentence**. Cases where you cannot are *Policy* questions — collect them, ask
   in one batch, do not guess.
3. Write scenarios in batches of 5–10 per PR, grouped by stage. Each PR lists
   which catalogue rows it covers.
4. When a scenario fails against current code, decide: is the expectation
   wrong, or the app? If the app, that is a found bug — file it; mark the
   scenario `skip: "BUG-123"` *only* if it cannot be fixed in the same PR, and
   report it.

Exit criteria: priorities 1–4 of the catalogue covered (typically 30–50
scenarios), every external error seen in production has a scenario, and the
open questions are answered or explicitly parked by a named owner.

## Phase 5 — CI gate

1. Copy `assets/templates/github-workflow-e2e.yml` (or the Azure DevOps one),
   adapt paths, and run it on the PR that adds it.
2. Measure wall-clock time; add shards or build caching to stay under 10 min.
3. Ask a repository admin to make the check required (you usually cannot do
   this yourself — say so explicitly in the report).
4. Add to the PR template: "Behaviour change? Scenario added/updated: ___".

Exit criteria: the check runs on every PR, is required on the default branch,
and uploads JUnit + diagnostics on failure.

## Phase 6 — Prove it catches bugs, then keep it alive

**Mutation round** — the only evidence the suite works. On a throwaway branch,
introduce realistic bugs one at a time and confirm a scenario fails for each.
Generic mutation classes to try on the flow under test:

| Mutation class | Example |
|---|---|
| Drop a validation | remove a status/permission/limit check |
| Off-by-one at a boundary | `<` ↔ `<=` on a limit or date |
| Wrong ordering | reverse a sort that decides allocation or priority |
| Wrong rounding | half-up ↔ half-even |
| Wrong field or sign in an outbound payload | swap two amount fields, negate a value |
| Wrong tenant/company | hard-code one instead of the mapping |
| Retry policy | retry a 4xx; stop retrying a 429 |
| Idempotency guard removed | allow re-processing a completed item |
| Trusting a bad success | mark done when the response lacks the external id |

Every mutation that survives is a missing scenario: write it and re-run the
mutation. Expect survivors: a first suite usually misses at least one
ordering or boundary rule that only a mutation reveals.

**Keeping it alive**:

- Behaviour-changing PRs update expectations in the same PR.
- Every production incident on the path gets a `REG` scenario before its fix is
  merged.
- Review skipped scenarios monthly; the count trends to zero.
- Bump pinned Postgres/WireMock/action versions deliberately, one per PR.

## Questions only humans can answer

Ask in one batch, with the scenario each one blocks:

1. Which external systems and versions, and is there a sandbox for the nightly
   contract job?
2. The business policies behind every *Policy* row of the catalogue.
3. What should happen after an unknown outcome (timeout after send)?
4. Copies of real error messages from logs (or access to the logs).
5. The manual regression checklist the team runs today, and recent incidents.

## Final report template

```
E2E scenario suite — status
- Stack: <postgres version>, WireMock <version>, app image from PR
- Scenarios: <N> (<n> per stage ...); <k> skipped (tickets: ...)
- Runtime on CI: <m> min across <s> shards
- Mutation round: <x>/<y> mutations caught; survivors and the scenarios added for them
- Bugs found while writing scenarios: <list with tickets>
- Not covered yet: <catalogue rows> — reason
- Needs a human: make the check required; answer policy questions <list>
```
