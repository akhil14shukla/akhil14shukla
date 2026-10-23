# Worked example: a tiny AR service under scenario tests

A runnable miniature of the real thing: `app.py` records receipts, matches them
to invoices, validates, and posts to a Dynamics 365 F&O-style API (Entra token →
journal header → lines → post), retrying throttled calls. The 17 scenarios in
`scenarios/` cover matching, validation, and posting failure modes, and all
pass. Use it to see the whole loop working before adapting it to your app.

## Run it (about a minute)

Needs Python 3.10+, `uv` (or `pip install "psycopg[binary]" pyyaml`), Java 17+
or Docker for WireMock, and a Postgres 14+ reachable as
`postgres:postgres@localhost:5432` (override with `E2E_ADMIN_DSN` / `E2E_DSN`).

```bash
SKILL=.claude/skills/scenario-e2e-testing      # adjust to where the skill lives

# 1. WireMock with the D365 default mappings (pick one)
docker run -d --name wm -p 8080:8080 -v "$PWD/$SKILL/assets/wiremock-d365:/home/wiremock" wiremock/wiremock:3.13.1
# java -jar wiremock-standalone-3.13.1.jar --port 8080 --root-dir $SKILL/assets/wiremock-d365

# 2. Database
uv run $SKILL/scripts/scenario_runner.py --config $SKILL/assets/example/e2e.config.yaml prepare

# 3. The app, with test hooks on
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ar_e2e MSD_BASE_URL=http://localhost:8080 \
  E2E_TEST_HOOKS=1 uv run $SKILL/assets/example/app.py &

# 4. Scenarios
uv run $SKILL/scripts/scenario_runner.py --config $SKILL/assets/example/e2e.config.yaml run
```

Expected: `17/17 scenarios passed`, about 0.2 s each.

## What to look at

| File | Shows |
|---|---|
| `e2e.config.yaml` | Every runner setting, annotated |
| `schema.sql`, `seed_base.sql` | Schema stand-in (real apps use `migrate_command`) and reference data |
| `fixtures/two_open_invoices_c001.sql` | A shared row graph several scenarios reuse |
| `scenarios/AR-MATCH-*.yaml` | Full flows through the API (create → match) with end-state rows |
| `scenarios/AR-POST-001_*.yaml` | Asserting exact payloads and call order sent to Dynamics |
| `scenarios/AR-POST-003_*.yaml` | Stateful stub: throttled once, then succeeds |
| `scenarios/AR-POST-004_*.yaml` | D365 validation error: no retry, message stored, nothing else moved |
| `scenarios/AR-VAL-*.yaml` | Negative paths asserting nothing changed and Dynamics was never called |
| `scenarios/AR-MATCH-006_*.yaml` | The scenario a mutation round added (reversed allocation order survived the other 16) |

## Try the mutation round

Break the app on purpose and watch the right scenario fail:

```bash
sed -i 's/if receipt\["on_hold"\]:/if False:/' $SKILL/assets/example/app.py   # drop the credit-hold check
# restart the app, run the scenarios: AR-VAL-001 fails ("expected HTTP 422, got 200")
git checkout -- $SKILL/assets/example/app.py
```
