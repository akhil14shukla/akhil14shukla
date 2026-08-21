---
name: <feed>-reconciliation
description: <What is compared to what, and why it exists — then the words a
  person will actually type when they need it: the file name, the systems, the
  metric, the ritual ("month-end close"), and the symptom ("payouts don't match
  the ledger"). Written as when to use, not as a summary of contents.>
---

# <Feed> reconciliation

<!-- One paragraph: what these two datasets are, who cares about the answer, and
     what goes wrong if the check is skipped. Method, adversarial checks, and
     report shape come from `ground-truth-analysis` — do not restate them here.
     Everything below should be something a competent analyst could NOT have
     guessed from the method alone. -->

## The contract

| | Ground truth | Candidate |
|---|---|---|
| Source | <system, table/report, how produced> | <system, file, how produced> |
| Grain | <one row = ?> | <one row = ?> |
| Key | <columns, and how they normalise> | <columns> |
| Scope | <filters, statuses, entities, date range> | <filters> |
| As-of | <timezone, cut time, settling behaviour> | <timezone, cut> |
| Units / sign | <currency, scale, sign convention> | <> |
| Files / period | <one file per what? naming convention, where they land> | <> |
| Vintage | <does a row change after export? which vintage is the truth?> | <> |

- **Authority**: <why the truth side wins, and what would make it the wrong
  reference for this question>
- **Tolerance**: <value + where the number came from>
- **Materiality**: <value + who set it>
- **Known-good baseline**: <last period verified by hand, and by whom>

## Column dictionary

<!-- Every column that matters, and what it is FOR — the section that stops the
     next person comparing three numeric columns and ignoring the one that
     explains the gap. Roles: identity / temporal / dimension / measure /
     derived / metadata. See `ground-truth-analysis` → `references/column-semantics.md`. -->

| Column | Role | Means | Additivity / units | Watch out for |
|---|---|---|---|---|
| <name> | <role> | <in business terms> | <additive? currency? scale?> | <trap> |

- **Slice every difference by**: <the dimension and lineage columns that have
  historically located the cause here>
- **Derived columns to recompute on each side**: <e.g. gross = qty x unit_price>
- **Dependencies that must hold**: <e.g. sku -> category, region -> currency>

## Assumptions that had to be resolved

<!-- The questions this comparison raised the first time, and the answers.
     This is the section that saves the next person a day. -->

- <question> → <answer, and who confirmed it>

## Run order

1. <step — the command, query, or check, with the flag values that matter>
2. <step>
3. <step — including checks that usually find nothing but are cheap insurance,
   marked "(usually clean, keep anyway because …)">

```bash
<the actual command, with real paths and thresholds>
```

## Known causes, most common first

| Cause | Signature | Test | Typical size | Status |
|---|---|---|---|---|
| <mechanism> | <what it looks like in the output> | <the check that confirms or kills it> | <rows / amount> | open / fixed <date> |

**Ruled out previously** (do not re-investigate without new evidence):
<cause — why it was excluded, date>

## Reporting

- Goes to: <people/channel>, by <when>
- Format: bridge table + one section per cause; see `ground-truth-analysis`
  → `references/reporting.md`
- Escalate immediately if: <the condition that cannot wait for the write-up>

## Done check

<!-- The specific version, not the generic one: which numbers must tie, which
     exhibits must exist, what must be filed and where. -->

- [ ] <bridge closes to zero, or residual under <x> and characterised>
- [ ] <the specific totals that must tie, named>
- [ ] <report delivered to the named audience>

*Last verified against a hand-checked period: <date>, <period>.*
