# Use case: accounts receivable posting to Microsoft Dynamics 365

For an application that ingests customer receipts, matches them against open
invoices, validates them, and posts them to Microsoft Dynamics 365 — with its own
data in Postgres. The pack assumes Dynamics 365 **Finance & Operations** (OData
`/data/` entities plus a custom posting service) and notes where Business
Central and Dataverse differ.

It adds to the generic method; it does not replace it. For each phase of
`references/adoption-playbook.md`, read the matching section of this pack's
`playbook.md`.

## What is in the pack

Paths are relative to the skill root.

| If you are… | Read / use |
|---|---|
| Applying the generic playbook to a Dynamics AR app: discovery greps, config keys, Entra ID setup, mutation list, questions for finance | `use-cases/dynamics-365-ar/playbook.md` |
| Identifying which Dynamics API the app calls, faking Entra ID + D365, D365-specific error catalogue, `$metadata` contract checks | `use-cases/dynamics-365-ar/dynamics-mock.md` |
| Choosing which AR cases to cover (ingestion, customer identification, matching, FX/rounding, validation, posting, reversal, concurrency) | `use-cases/dynamics-365-ar/ar-case-catalog.md` |
| Copying ready-made WireMock stubs: defaults (token, journal header/lines/post) and failure modes (429, 400, 503, reset, slow, expired secret, 401) | `use-cases/dynamics-365-ar/wiremock-d365/mappings/`, `use-cases/dynamics-365-ar/wiremock-d365/stubs/` |
| Seeing the whole loop run: a small AR service, config, schema, fixtures, and 17 passing scenarios | `use-cases/dynamics-365-ar/example/` — start with `use-cases/dynamics-365-ar/example/README.md`; scenarios in `use-cases/dynamics-365-ar/example/scenarios/`, fixtures in `use-cases/dynamics-365-ar/example/fixtures/` |

## Copying the pack into an application repository

```bash
SKILL=.claude/skills/scenario-e2e-testing
mkdir -p e2e/wiremock/mappings/d365 e2e/wiremock/stubs/d365
cp $SKILL/use-cases/dynamics-365-ar/wiremock-d365/mappings/*.json e2e/wiremock/mappings/d365/
cp $SKILL/use-cases/dynamics-365-ar/wiremock-d365/stubs/*.json    e2e/wiremock/stubs/d365/
```

Then rename paths and fields in the copied stubs to what the app's client
actually calls (`dynamics-mock.md` §1), and start the scenario list from
`ar-case-catalog.md`.
