# Dynamics 365 AR: additions to each adoption phase

Read this alongside `references/adoption-playbook.md`. Each section adds what is
specific to an accounts-receivable app posting to Microsoft Dynamics 365; the
generic steps and exit criteria still apply.

## Phase 0 — Discovery: extra searches

| Find | How to search | Why |
|---|---|---|
| Which Dynamics product the app calls | `grep -rniE "operations\.dynamics\.com|businesscentral|api\.businesscentral|crm[0-9]*\.dynamics\.com|/api/data/v9|/data/[A-Z]"` | F&O vs Business Central vs Dataverse (`dynamics-mock.md` §1) |
| Every D365 path and payload | grep the client for entity names (`CustomerPaymentJournal`, `LedgerJournal`, `customerPayments`, `journals`), `$batch`, `/api/services/` | Stub inventory |
| Entra ID setup | `grep -rniE "login\.microsoftonline|AuthorityHost|ConfidentialClientApplication|ClientSecretCredential|msal|azure.identity|oauth2/v2.0/token"` | Is the authority configurable? Token caching? |
| Company mapping | grep `dataAreaId`, `company`, `legal_entity`, `LegalEntity` | Wrong-company posting is a top risk |
| AR tables | receipts/payments, invoices/open items, allocations/applications/settlements, customers, posting batches/journals, statuses, audit | `snapshot.tables`, state machines |
| Matching engine and its settings | grep `tolerance`, `write_off`, `discount`, `match`, `allocate`, `remittance` | Policy rows of the catalogue |
| Posting trigger | API endpoint, background job, or queue consumer that posts to D365 | Job hook or direct `request` step |
| Status sync / reconciliation jobs | grep `sync`, `reconcile`, `voucher` | AR-SYNC / AR-REC scenarios |

## Phase 1 — Harness: Dynamics-specific settings

- Database name, e.g. `ar_e2e`; `snapshot.tables` for receipts, invoices,
  allocations, customers, and the posting/journal table.
- Compose `app` environment: map the app's real keys to the fake, e.g.

  ```yaml
  MSD_BASE_URL: http://wiremock:8080                                  # D365 environment URL
  MSD_TOKEN_URL: http://wiremock:8080/<tenant-id>/oauth2/v2.0/token   # Entra authority, pointed at the fake
  MSD_CLIENT_ID: e2e
  MSD_CLIENT_SECRET: e2e
  MSD_RETRY_MAX_BACKOFF_MS: "50"
  MSD_HTTP_TIMEOUT_S: "2"
  ```

- Copy the pack's stubs into `e2e/wiremock/` (pack `README.md`).

## Phase 2 — Hooks: what usually needs changing in AR apps

- **Clock**: posting date, period-closed checks, discount and due-date logic.
- **Jobs**: auto-match sweep, posting queue, retry sweeper, D365 status sync.
- **Caches**: Entra token cache (MSAL/Azure.Identity caches per process), FX
  rates, company/legal-entity mapping.
- **Authority**: MSAL `authority` / Azure.Identity `AuthorityHost` from config.

## Phase 3 — The Dynamics fake

1. Rename the pack's default stubs to the app's real entity, field, and
   custom-service names. Verify against the environment's `$metadata`.
2. Replace illustrative error bodies with real ones from production logs
   (`dynamics-mock.md` §4 lists the D365 errors to look for).
3. First posting scenario: assert company (`dataAreaId`), account, amount and
   side (`CreditAmount`), currency, `TransDate` against the scenario clock,
   invoice mark, payment reference, and the header → lines → post order.

## Phase 4 — Catalogue

Start from `ar-case-catalog.md`, in its §9 priority order. Its *Policy* rows
are the questions for the finance owner (below).

## Phase 6 — Mutation list for AR apps

| Mutation | Should be caught by |
|---|---|
| Drop the credit-hold check | AR-VAL-001 |
| Retry only on 503, not 429 | AR-POST-003 |
| Reverse allocation order | AR-MATCH-006 |
| Round half-even instead of half-up (or vice versa) | AR-RND-003 |
| Send `DebitAmount` instead of `CreditAmount` | AR-POST-001 payload assertion |
| Hard-code `dataAreaId` instead of the entity mapping | AR-POST-011 |
| Retry a 400 | AR-POST-004 (call count) |
| Mark posted when the response lacks a voucher | AR-POST-013 |
| Remove the already-posted guard | AR-VAL-003 |
| Re-post after a timeout without a lookup | AR-POST-007 |

## Questions for finance and the Dynamics owner

1. Which Dynamics product and version; is there a UAT/sandbox environment for
   the nightly contract job?
2. Matching policy: tolerances (absolute and %), write-off accounts, allocation
   order, subset matching on/off, third-party payments, credit-note netting.
3. Posting policy: posting date (receipt date vs today), behaviour when the
   period is closed, approval thresholds, batch sizes, one journal per receipt
   or per batch.
4. What should happen after a timeout while posting (unknown outcome)?
5. Real D365 error messages from logs, the manual regression checklist, and the
   last year's AR incidents.
