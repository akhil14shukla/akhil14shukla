# Use-case packs

The generic method lives in `references/` and `assets/templates/`. A **use-case
pack** adds everything specific to one kind of application and the external
system it integrates with, so it can be applied without re-researching that
system. Read the generic reference for a phase first, then the pack's notes for
the same phase.

## Packs

| Pack | External system | Domain | Entry point |
|---|---|---|---|
| `dynamics-365-ar` | Microsoft Dynamics 365 (Finance & Operations; notes for Business Central and Dataverse) + Entra ID | Accounts receivable / cash application: receipts matched to invoices, validated, posted | `use-cases/dynamics-365-ar/README.md` |

## Choosing: full match, partial match, or none

Decide once, at the start, and write the decision into the target repo's
`e2e/README.md` so later sessions do not re-decide it.

| The app matches the pack's… | Use |
|---|---|
| External system **and** domain | The whole pack, on top of the generic files |
| External system only (e.g. Dynamics 365, but sales orders or procurement) | Generic files + the pack's system file (`dynamics-mock.md`) and the token/auth stubs. Not its domain catalogue, domain stubs, or example. |
| Domain only (e.g. accounts receivable, but posting to SAP or NetSuite) | Generic files + the pack's domain catalogue (`ar-case-catalog.md`), re-checked against the app's policies. Not its system file, stubs, or example. |
| Neither | Generic files only. Ignore `use-cases/` entirely. |

When unsure, treat it as no match: the generic method is complete without any
pack, while borrowing from the wrong pack plants another domain's assumptions
(entity names, payload fields, business rules) in the new suite.

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
