# Use-case packs

The generic method lives in `references/` and `assets/templates/`. A **use-case
pack** adds everything specific to one kind of application and the external
system it integrates with, so it can be applied without re-researching that
system. Read the generic reference for a phase first, then the pack's notes for
the same phase.

## Packs

| Pack | For | Entry point |
|---|---|---|
| `dynamics-365-ar` | Accounts receivable / cash application: receipts matched to invoices, validated, and posted to Microsoft Dynamics 365 (Finance & Operations; notes for Business Central and Dataverse), data in Postgres | `use-cases/dynamics-365-ar/README.md` |

## Anatomy of a pack

```
use-cases/<system>-<domain>/
├── README.md        what the pack covers, when to use it, a routing table to its files
├── playbook.md      per-phase additions to references/adoption-playbook.md:
│                    discovery greps, config keys, stubs, cases, mutations, questions
├── <system>-mock.md the system's API identification, auth, error catalogue mapped to
│                    references/external-services.md §6, recording and contract notes
├── <domain>-case-catalog.md   the domain's case list (output of case-catalogue-method.md)
├── wiremock-<system>/
│   ├── mappings/    boot-time defaults: token + happy path
│   └── stubs/       opt-in failure modes
└── example/         a small runnable app + config + fixtures + passing scenarios
```

## Adding a pack

1. Copy the anatomy above under `use-cases/<system>-<domain>/`.
2. Keep generic material out: if a paragraph would apply to any external
   system, it belongs in `references/` instead.
3. Make the example runnable and passing; run a mutation round on it.
4. Add a row to the table above and route to the pack's README from
   `SKILL.md`. The pack's README must name every one of the pack's files or
   directories (the suite's `validate.py` checks this).
