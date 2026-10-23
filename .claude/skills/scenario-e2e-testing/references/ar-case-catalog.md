# Accounts-receivable case catalogue

Read this when building the initial scenario list for a cash-application /
receipt-matching / ERP-posting system, or when checking a suite for gaps. It is
a checklist of cases such systems get wrong, grouped by stage. Each row is one
or more scenarios.

**Expected outcomes are policy.** Where the right answer depends on the
business (tolerance, write-off authority, allocation order), the row says
*Policy* and names the question. Get the answer from the finance owner and write
it into the scenario — never let the current code's behaviour become the
expected value by default. Rows marked ✓ have a runnable example in
`assets/example/scenarios/`.

## Contents

1. Receipt ingestion
2. Customer identification
3. Matching and allocation
4. Money: currency, rounding, discounts, deductions
5. Pre-posting validation
6. Posting to Dynamics
7. After posting: reversal, unapply, status sync, reconciliation
8. Concurrency and re-runs
9. Building the first suite: priority order

## 1. Receipt ingestion

| ID | Case | Expected |
|---|---|---|
| AR-RCPT-001 ✓ | Same receipt (bank reference) delivered twice | Second rejected or ignored idempotently; one row |
| AR-RCPT-002 | Same amount, same customer, same day, *different* bank references | Two receipts — not deduplicated |
| AR-RCPT-003 | Zero or negative amount | Rejected with reason; *Policy* for negative (bank return/reversal) |
| AR-RCPT-004 | Unknown currency code / currency not enabled for the legal entity | Rejected or parked; nothing posted |
| AR-RCPT-005 | Amount with more decimals than the currency allows (`100.005` USD, `100.5` JPY) | Rejected or rounded per *Policy*; never silently truncated |
| AR-RCPT-006 | Remittance reference with noise: lowercase, spaces, `INV 1001`, `INV-001001`, Unicode dash, trailing punctuation, 35-char truncation | Normalised and matched, or parked; assert which |
| AR-RCPT-007 | Remittance listing several invoices with amounts per invoice | Allocations follow remittance amounts, not oldest-first |
| AR-RCPT-008 | Bank file re-delivered with one changed line | New line ingested, unchanged lines not duplicated |
| AR-RCPT-009 | Value date in a closed period / in the future | *Policy*: accepted with adjusted posting date, or parked |
| AR-RCPT-010 | Receipt for a legal entity / bank account not mapped to a Dynamics company | Parked with mapping error; no ERP calls |

## 2. Customer identification

| ID | Case | Expected |
|---|---|---|
| AR-CUST-001 | Customer account number on the receipt | Direct identification |
| AR-CUST-002 | No account; invoice reference belongs to a unique customer | Customer inferred from invoice |
| AR-CUST-003 | Invoice reference belongs to a *different* customer than the payer account | *Policy*: third-party payment allowed (parent pays for child) or exception |
| AR-CUST-004 | Payer name only, fuzzy match to two customers | Exception queue — never guess between two |
| AR-CUST-005 | Customer exists in the app but not in Dynamics (or blocked there) | Fails at posting with D365 error, or pre-validated; assert which |
| AR-CUST-006 | Parent/child (corporate group) accounts | Matching across the group per *Policy* |
| AR-CUST-007 | Customer merged/renamed; old account on the receipt | Mapped to surviving account |

## 3. Matching and allocation

| ID | Case | Expected |
|---|---|---|
| AR-MATCH-001 ✓ | Exact reference, exact amount | Invoice paid, receipt matched |
| AR-MATCH-002 ✓ | Exact reference, short payment | Invoice partially paid; open amount reduced exactly |
| AR-MATCH-003 ✓ | Exact reference, overpayment | Invoice paid, excess unapplied / on-account |
| AR-MATCH-004 ✓ | No reference; amount equals total open balance | All invoices paid |
| AR-MATCH-005 ✓ | Currency differs from all open invoices | Unmatched; invoices untouched |
| AR-MATCH-006 ✓ | Several invoices referenced, amount covers only some | Allocation order per *Policy* (oldest due first, or remittance order) |
| AR-MATCH-007 | No reference; amount equals exactly one open invoice | Matched to it — *Policy*: only if unique; two invoices with the same amount → exception |
| AR-MATCH-008 | No reference; amount equals a *subset* sum of open invoices | *Policy*: subset matching on or off; if on, ambiguity (two subsets) → exception |
| AR-MATCH-009 | Short payment within tolerance (absolute and %) | Invoice paid, difference written off to the configured account |
| AR-MATCH-010 | Short payment exactly at the tolerance boundary, and 0.01 beyond | Boundary inclusive/exclusive per *Policy*; two scenarios |
| AR-MATCH-011 | Reference to an invoice already paid | Exception / on-account; never double-applied |
| AR-MATCH-012 | Reference to a credit note | Credit applied or ignored per *Policy* |
| AR-MATCH-013 | Credit notes open on the account: net invoice minus credit equals receipt | Both settled per *Policy* |
| AR-MATCH-014 | Disputed / on-hold invoice is the only candidate | Not matched automatically |
| AR-MATCH-015 | Invoice exists in the app but was cancelled/reversed | Not matched |
| AR-MATCH-016 | One invoice paid by two receipts (instalments) | Second receipt closes it; open amount 0, never negative |
| AR-MATCH-017 | Receipt arrives before the invoice is synced | Unmatched now; matched on re-run after invoice arrives |
| AR-MATCH-018 | Manual match overrides auto-match suggestion | Manual allocation stored exactly; auto-match does not re-run over it |
| AR-MATCH-019 | Unmatch (undo) before posting | Allocations removed, invoices restored to prior open amounts |

## 4. Money: currency, rounding, discounts, deductions

| ID | Case | Expected |
|---|---|---|
| AR-FX-001 | Receipt currency ≠ invoice currency, rate table has the date | Converted with the rate *for the right date* (*Policy*: receipt date vs posting date) |
| AR-FX-002 | Rate missing for the date | Parked; no posting |
| AR-FX-003 | Realised FX gain/loss on settlement | Difference posted to the FX account, amount exact |
| AR-RND-001 | Allocation splitting creates a third of a cent (100.00 over 3 invoices) | Sum of allocations equals receipt exactly; remainder rule per *Policy* |
| AR-RND-002 | Currency with 0 decimals (JPY) and 3 decimals (KWD/BHD) | No `.00` assumptions; values sent to D365 match the currency |
| AR-RND-003 | Half-cent rounding (`.005`): half-up vs banker's | Matches the ERP's rounding, or posting will be off by a cent |
| AR-DISC-001 | Early-payment discount, paid on the last discount day | Discount taken |
| AR-DISC-002 | Same, paid one day late | No discount; short payment handling applies |
| AR-DED-001 | Short payment coded as deduction (chargeback, promotion, freight) | Deduction record created; invoice closed or kept open per *Policy* |
| AR-DED-002 | Bank charges deducted by the payer's bank | Written off to bank charges within limit |

## 5. Pre-posting validation

| ID | Case | Expected |
|---|---|---|
| AR-VAL-001 ✓ | Customer on credit hold | Refused before any ERP call; nothing changes |
| AR-VAL-002 ✓ | Posting period closed (app-side calendar) | Refused; nothing changes |
| AR-VAL-003 ✓ | Already posted | Refused; no second journal |
| AR-VAL-004 ✓ | Not matched | Refused |
| AR-VAL-005 | Sum of allocations ≠ receipt amount − unapplied (data corruption) | Refused with integrity error |
| AR-VAL-006 | Missing financial dimensions / posting profile / ledger mapping | Refused with the missing mapping named |
| AR-VAL-007 | Posting date on the last day of a period, clock just after midnight UTC but still the old day in the legal entity's time zone | Period decided in the entity's time zone |
| AR-VAL-008 | User lacks permission to post (if posting is user-triggered) | 403; nothing changes |
| AR-VAL-009 | Amount above an approval threshold | Routed to approval, not posted |

## 6. Posting to Dynamics

The failure modes and their stubs are in `dynamics-mock.md` §5. Minimum set:

| ID | Case | Expected |
|---|---|---|
| AR-POST-001 ✓ | Happy path | Exact payloads, order, voucher stored |
| AR-POST-002 ✓ | Overpayment posts on-account line | Extra line without invoice mark |
| AR-POST-003 ✓ | Throttled once (429) | Retried after `Retry-After`; posted once |
| AR-POST-004 ✓ | D365 validation error on a line | No post call; D365 message stored; no retry |
| AR-POST-005 ✓ | 503 on every attempt | Exactly N attempts; retryable failure state |
| AR-POST-006 ✓ | Expired client secret | No data calls; clear error |
| AR-POST-007 | Timeout / connection reset after send | Outcome unknown → reconciliation, not blind repost |
| AR-POST-008 | Partial journal (some lines created, one rejected) | No posting of partial journal; retry does not duplicate lines |
| AR-POST-009 | Retry after a fixed failure | One journal in total; error cleared; status posted |
| AR-POST-010 | Payment already exists in D365 (duplicate reference) | Linked, not reposted |
| AR-POST-011 | Multi-company: receipt for entity GB01 | `dataAreaId` = GB01's company on every call |
| AR-POST-012 | Large receipt with many allocations (above the app's batch size) | Split into the documented number of journals/batches; totals reconcile |
| AR-POST-013 | Success response missing the voucher | Not marked posted with a null voucher |
| AR-POST-014 | Token expires mid-run | One refresh, no duplicate lines |

## 7. After posting: reversal, unapply, status sync, reconciliation

| ID | Case | Expected |
|---|---|---|
| AR-REV-001 | Reverse a posted receipt (bounced payment) | Reversal journal posted in D365, invoices reopened, receipt `reversed` |
| AR-REV-002 | Reverse when the original period is now closed | Reversal dated in the open period per *Policy* |
| AR-REV-003 | Unapply one allocation of a posted multi-invoice receipt | Only that invoice reopens; D365 call settles/unsettles exactly that line |
| AR-SYNC-001 | Status sync: D365 shows posted, app shows unknown | App updated to posted with voucher |
| AR-SYNC-002 | Status sync: D365 has no record of an "unknown outcome" posting | App returns it to retryable |
| AR-REC-001 | Daily reconciliation: app total ≠ D365 total | Discrepancy report lists the receipt; no automatic correction |

## 8. Concurrency and re-runs

Black-box scenarios run one request at a time; express concurrency with
mid-scenario `sql` steps (simulate the other actor) or with two requests whose
interleaving the app must handle.

| ID | Case | Expected |
|---|---|---|
| AR-CONC-001 | Two receipts matched to the same last open invoice | Second sees the reduced open amount; invoice never over-applied (row lock / constraint) |
| AR-CONC-002 | Post called twice quickly (double-click, retry by a load balancer) | Exactly one journal |
| AR-CONC-003 | Invoice edited (amount changed) between match and post | Post refused or re-validated |
| AR-CONC-004 | Matching job re-run over already-processed receipts | No changes (idempotent) — `db_unchanged` on everything |

## 9. Building the first suite: priority order

1. **One happy path per stage** (ingest → match → validate → post) to prove the
   wiring.
2. **Every incident and production bug of the last 12 months** (AR-REG-*).
   These are the cases that already cost money.
3. **Money-integrity cases**: double posting (AR-VAL-003, AR-POST-007/009/010,
   AR-CONC-002), over-application (AR-MATCH-011, AR-CONC-001), rounding
   (AR-RND-*), wrong company (AR-POST-011).
4. **Every D365 error** you have seen in production logs, with its real body.
5. **Policy boundaries**: tolerance ±0.01, discount date ±1 day, period
   boundaries.
6. Everything else, ordered by how often the manual testers check it today.

Thirty to fifty scenarios covering 1–4 replace most of a manual regression pass.
