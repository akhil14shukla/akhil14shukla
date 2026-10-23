# Running the suite locally and on every PR

Read this when installing the runner in a repository, writing the config,
wiring CI so the suite gates pull requests, sharding for speed, or deciding to
drive scenarios from an in-process test framework instead.

## Contents

1. Installing the runner
2. Configuration reference
3. The local loop
4. CI: gating every pull request
5. Speed: budget, sharding, what to cut
6. Alternative: in-process tests reading the same YAML
7. Flakes, quarantine, and ownership
8. Extending the runner

## 1. Installing the runner

Copy `scripts/scenario_runner.py` to `<repo>/e2e/scenario_runner.py`. It is a
single file with two dependencies (`psycopg[binary]`, `PyYAML`) declared inline
(PEP 723), so `uv run e2e/scenario_runner.py ...` needs no setup. Without uv:
`pip install "psycopg[binary]" pyyaml` then `python e2e/scenario_runner.py`.
It works the same whatever language the application is written in.

```bash
uv run e2e/scenario_runner.py --config e2e/e2e.config.yaml prepare       # create + migrate DB
uv run e2e/scenario_runner.py --config e2e/e2e.config.yaml list          # ids, tags, files
uv run e2e/scenario_runner.py --config e2e/e2e.config.yaml run           # everything
uv run e2e/scenario_runner.py --config e2e/e2e.config.yaml run --filter ORD-PAY --filter regression
uv run e2e/scenario_runner.py --config e2e/e2e.config.yaml run --shard 2/4 --junit e2e/out/junit.xml
uv run e2e/scenario_runner.py --config e2e/e2e.config.yaml run --filter ORD-PAY-007 --capture e2e/out/actual
```

Exit codes: `0` all passed, `1` at least one scenario failed, `2` the harness
could not run (bad config, app not ready, nothing selected).

## 2. Configuration reference

Annotated template: `assets/templates/e2e.config.yaml` (a filled-in, working
config is in each use-case pack's `example/`). `${VAR}` and
`${VAR:-default}` are expanded from the environment so CI can override.

| Key | Meaning |
|---|---|
| `database.admin_dsn` | Connection to the `postgres` maintenance DB, for create/drop |
| `database.dsn` | The database the app uses; the runner seeds and asserts here |
| `database.reset` | `truncate` (default) or `template` — see `architecture.md` §5 |
| `database.template` | Template DB name (template mode) |
| `database.schemas` | Schemas to truncate / restart sequences in (default `[public]`) |
| `database.keep_tables` | Tables never truncated: migration history, static lookup tables seeded by migrations |
| `database.migrate_command` | The app's migration command; receives the DSN in `url_env` |
| `database.url_env` | Env var name for that DSN (default `DATABASE_URL`) |
| `database.schema_files` | Plain SQL schema files, if there is no migration tool |
| `database.base_seed` | SQL files applied after every reset (truncate) or baked into the template |
| `app.base_url` | Where the running app listens |
| `app.headers` | Sent on every request (auth for the API under test) |
| `app.ready` | `{path, timeout_s}` polled before the first scenario |
| `app.clock` | Request template sent when a scenario has `clock` (`{{clock}}` substituted) |
| `mock.admin_url` | WireMock base URL; omit if the app calls no external HTTP system |
| `snapshot.ignore_columns` | Volatile columns ignored by `db_unchanged` and `--capture` |
| `snapshot.tables` | Tables `--capture` dumps, with `key` (sort) and per-table `ignore_columns` |
| `scenarios` | Glob patterns relative to the config file |

API authentication: give the app an e2e-only static token or test identity
provider; put it in `app.headers`. Do not disable auth in e2e mode — auth
middleware is part of what ships.

## 3. The local loop

```bash
docker compose -f e2e/docker-compose.e2e.yml up -d --wait postgres wiremock
uv run e2e/scenario_runner.py --config e2e/e2e.config.yaml prepare
# run the app from your IDE with the e2e env vars (debugger works), or:
docker compose -f e2e/docker-compose.e2e.yml up -d --build --wait app
uv run e2e/scenario_runner.py --config e2e/e2e.config.yaml run --filter ORD-ALLOC
```

Running the app from the IDE against the same Postgres and WireMock gives
breakpoints in the code path a failing scenario exercises. Re-run `prepare`
only after a migration changes.

Offer a one-word entry point in the repo's task runner:

```make
e2e:            ## run all scenarios against a fresh stack
	docker compose -f e2e/docker-compose.e2e.yml up -d --wait postgres wiremock
	uv run e2e/scenario_runner.py --config e2e/e2e.config.yaml prepare
	docker compose -f e2e/docker-compose.e2e.yml up -d --build --wait app
	uv run e2e/scenario_runner.py --config e2e/e2e.config.yaml run
```

## 4. CI: gating every pull request

Templates: `assets/templates/github-workflow-e2e.yml` (GitHub Actions) and
`assets/templates/azure-pipelines-e2e.yml` (Azure DevOps — common in
Microsoft-stack shops). Both do the same five things:

1. Start Postgres and WireMock (`docker compose up -d --wait`).
2. `prepare` — create and migrate the database.
3. Build and start the app image from the PR's code.
4. `run --shard i/n --junit ...` — scenarios for this shard.
5. Always upload `e2e/out/` (JUnit, captures) and, on failure, compose logs and
   the WireMock journal; publish the JUnit report so failures show inline.

Then make it a **gate**:

- GitHub: Settings → Branches → branch protection (or rulesets) → require the
  `e2e` check(s) to pass before merging. With a matrix, require each shard's
  check name, or add a final `e2e-result` job that `needs` all shards and
  require only that.
- Azure DevOps: Branch policies → Build validation → add the pipeline as
  required.

Rules that keep the gate trustworthy:

- **Run on every PR**, with no path filters. Changes in "unrelated" config,
  migrations, or dependency bumps are exactly what breaks integrations.
- **No secrets needed.** The stack is hermetic; that is why it can run on fork
  PRs too. If someone adds a real credential to make a scenario pass, the
  design has been broken.
- **Same images as production** for the app (build from the PR's Dockerfile)
  and the same Postgres major version.
- **Pin tool versions** (Postgres, WireMock, actions) and bump deliberately.

## 5. Speed: budget, sharding, what to cut

Budget: under 10 minutes from push to result. Measure where it goes — the
runner prints seconds per scenario; CI shows build time.

- **Image build** usually dominates: cache layers (`docker/build-push-action`
  with `cache-from: type=gha`, or the Azure equivalent).
- **Sharding**: `--shard i/n` assigns each scenario by a hash of its id, so
  shards are stable as scenarios are added. Add a shard when one exceeds ~8 min.
- **Per-scenario cost** above ~1 s means a slow app path, a large base seed,
  or retry back-off not capped in e2e mode — fix the cause.
- **Do not cut assertions** for speed; they are almost free.

## 6. Alternative: in-process tests reading the same YAML

When the team wants scenarios inside the app's own test framework (debugger,
parallel workers, code coverage), keep the YAML as the format and write a thin
loader. The semantics in `scenario-format.md` stay the same; only the plumbing
moves:

| Concern | In-process approach |
|---|---|
| Discovery | One parametrised test per YAML file (`pytest.mark.parametrize`, xUnit `[Theory] + MemberData`, JUnit `@ParameterizedTest @MethodSource`, Jest `test.each`) named by scenario id |
| Database | Testcontainers Postgres once per run; per test `CREATE DATABASE t_<worker>_<n> TEMPLATE tpl` and point the app's DI container at it — enables parallel workers |
| App | Framework test host: FastAPI `TestClient`, ASP.NET `WebApplicationFactory`, Spring `@SpringBootTest(webEnvironment=RANDOM_PORT)`, supertest |
| External fakes | Same WireMock (Testcontainers module or standalone) and the same stub files; one WireMock per worker, or isolate by a unique tenant/company/path per test |
| Clock | Replace the clock service in DI instead of the HTTP hook |
| Matching rules | Port `match_value` and `check_table` (≈150 lines) from the runner, or call the runner's functions if the app is Python |

Keep the black-box runner in CI even then: it is the one that tests the
shipped container.

## 7. Flakes, quarantine, and ownership

- A scenario that fails intermittently is a bug in determinism (see
  `architecture.md` §7) or a real race in the app. Reproduce with
  `run --filter <id>` in a loop; the cause is almost always an uncontrolled
  clock, an async job, a cache, or unordered results.
- Quarantine only with `skip: "<reason> <ticket>"` in the scenario, which the
  runner reports as not selected; never delete or weaken assertions to go
  green. Track skipped scenarios to zero.
- **The PR that changes behaviour updates the scenarios.** A reviewer reads
  the expected-value diff as the description of the behaviour change.
- New feature or bug fix PRs add at least one scenario; put that in the PR
  template checklist.

## 8. Extending the runner

The runner is deliberately small (one file) so a project can own it. Common,
safe extensions:

- **Another external system** (bank API, tax service, email): another WireMock
  instance or path prefix, and the same `mock_requests` style assertions.
- **Message queues** (Service Bus, RabbitMQ, Kafka): a step type that publishes
  a message, and a `then` key that reads a test-only queue/topic; or have the
  app expose `POST /__test/jobs/consume-once`.
- **File outputs** (bank files, reports): a `then.files` key comparing a
  produced file to a committed golden file after normalising volatile fields.
- **Per-scenario config overrides**: a `when` step calling an app hook that
  sets a feature flag for the scenario.

Keep extensions generic and in the runner, not as one-off code in scenarios.
