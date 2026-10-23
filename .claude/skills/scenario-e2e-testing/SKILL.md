---
name: scenario-e2e-testing
description: Build and run end-to-end tests in which every scenario starts from a hand-written Postgres state, calls the real API, and asserts the exact end state — HTTP responses, database rows, and the calls made to external systems (faked with WireMock) — and gate every pull request on them. Use when replacing manual regression testing with automated E2E tests, "test against a seeded/local database", "golden dataset", "known-state tests", "mock the external API / ERP", "run e2e on every PR", turning incidents or manual test cases into automated ones, or adding a scenario to an existing suite. Generic method for any app, plus a ready use-case pack for accounts receivable posting to Microsoft Dynamics 365 (D365, F&O, Business Central, Entra ID).
---

# Scenario E2E testing

**If you wrote the starting database, you know the right answer.** Each
scenario is one YAML file stating one business rule as data:

- **given** the exact rows in Postgres and how each external system will behave,
- **when** these API calls are made against the real, running application,
- **then** these responses, these rows, no change to those tables, and exactly
  these calls (with these payloads) to the external systems.

The app runs as its shipped container against real Postgres (migrated by its
own migrations) and WireMock impersonating its external HTTP systems and their
identity provider. A runner resets everything before each scenario, so
scenarios are independent and run in any order, on any shard, on every PR.

The method is generic (`references/`, `assets/templates/`, `scripts/`) and is
complete on its own. System- and domain-specific knowledge lives in optional
**use-case packs** under `use-cases/`.

**Choose the pack before anything else, and record the choice** in the target
repo's `e2e/README.md`. A pack applies only when the app matches *both* its
external system and its domain (`use-cases/README.md` has the table). With no
match, use only the generic files: do not copy a pack's stubs, cases, scenario
ids, table names, or example code — they encode another domain's rules.

## The standing rules

1. **A human states the expected outcome before the scenario runs.** If you
   cannot, it is a policy question for the business owner — ask; never let the
   current code's output become the expectation.
2. **Black box at the edges.** Drive the app only through its public API; fake
   only at the network boundary (WireMock at the API and token URLs), never by
   mocking the app's own client classes.
3. **Real Postgres, real migrations,** production's major version. No SQLite,
   no in-memory substitutes, no production dumps as base state.
4. **Determinism is designed in**: the app's clock, background jobs and caches
   are controllable through test hooks enabled only by `E2E_TEST_HOOKS=1`, and
   the app refuses that flag in production. No `sleep`; poll with `wait_for`.
5. **Assert what must not happen.** Negative paths use `db_unchanged` and
   `{url_path_pattern: ".*", count: 0}` on external calls.
6. **Assert the payload sent out** — tenant/company, account, amount and sign,
   currency, date, reference — not merely that a call was made.
7. **Unknown outcomes are first-class.** Timeouts and resets after sending must
   have scenarios proving the app never blindly repeats the effect.
8. **PR builds are hermetic**: no real external systems, no secrets, no shared
   sandbox. A separate nightly contract job checks each fake against a sandbox.
9. **One rule per scenario, minimal rows.** Inline the rows the rule is about;
   fixtures for incidental context. Copy real error bodies into stubs.
10. **`--capture` output is a draft.** Cut it to the columns that matter and
    check each value by hand before committing.
11. **Prove the suite with a mutation round**: inject realistic bugs; each one
    that no scenario catches is a missing scenario.

## Adding one scenario to an existing suite

1. Find the case in the app's catalogue (`e2e/README.md`) or the incident.
2. Write the expected outcome as one sentence; then the YAML, copying the
   nearest existing scenario or `assets/templates/scenario.template.yaml`.
3. Run `uv run e2e/scenario_runner.py --config e2e/e2e.config.yaml run --filter <ID>`.
4. A regression scenario must fail against the unfixed code, for the reported
   reason, before the fix goes in.

## Before you call it done

Scenarios pass from a clean stack twice in a row and alone (`--filter`); each
new one asserts end-state rows, unchanged tables, and external calls; the CI
job runs on every PR and is (or is reported as needing to be) a required
check; and the report lists skipped scenarios, open policy questions, and which
mutation-round bugs the suite does not yet catch.

## Read the reference that matches your task

| If you are… | Read |
|---|---|
| Introducing this into an application from scratch — phased plan, discovery greps, questions for humans, report template | `references/adoption-playbook.md` |
| Designing the harness: components, reset strategy, where to fake, determinism, test hooks, repo layout | `references/architecture.md` |
| Writing or debugging a scenario: every key, matchers, variables, failure output, `--capture` | `references/scenario-format.md`, annotated `assets/templates/scenario.template.yaml` |
| Seeding: base seed vs fixtures, migrations per stack, harvesting a production case, anonymising, money/time traps | `references/database-and-fixtures.md` |
| Faking any external HTTP system and its identity provider; failure-mode catalogue; recording; contract job | `references/external-services.md` |
| Deciding which cases to cover in any domain: sources, lenses, policy questions, priority | `references/case-catalogue-method.md` |
| Running locally, config keys, CI gate, sharding, flakes, in-process alternative | `references/runner-and-ci.md`; templates `assets/templates/e2e.config.yaml`, `assets/templates/docker-compose.e2e.yml`, `assets/templates/github-workflow-e2e.yml`, `assets/templates/azure-pipelines-e2e.yml` |
| Running scenarios | `scripts/scenario_runner.py` (`prepare`, `list`, `run --filter/--shard/--junit/--capture`) |
| Checking for a ready use-case pack, or creating one | `use-cases/README.md` |
| Working on accounts receivable posting to Microsoft Dynamics 365 (stubs, AR case catalogue, per-phase notes, runnable example) | `use-cases/dynamics-365-ar/README.md` |
