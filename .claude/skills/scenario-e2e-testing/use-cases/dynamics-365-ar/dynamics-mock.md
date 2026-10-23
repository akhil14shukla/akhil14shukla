# Faking Microsoft Dynamics 365 and Entra ID

Read this when the external system is Dynamics 365. It holds only what is
specific to Dynamics; the mechanics (defaults vs opt-in stubs, priorities,
stateful stubs, faults, templating, recording, the generic failure catalogue,
the unknown-outcome rule) are in `references/external-services.md`. Ready stubs
are in this pack's `wiremock-d365/`.

## Contents

1. Which Dynamics? Identify the API first
2. Entra ID specifics
3. The pack's stub library
4. Dynamics failure modes mapped to the generic catalogue
5. Asserting a Dynamics posting
6. Recording and contract checks against a D365 sandbox

## 1. Which Dynamics? Identify the API first

"Microsoft Dynamics" is several products with different APIs. Find which one
the app calls (pack `playbook.md`, Phase 0) before writing any stub.

| Product | Base URL shape | Typical AR objects | How posting is usually done |
|---|---|---|---|
| **Finance & Operations** (D365 Finance, "F&O", formerly AX) | `https://<env>.operations.dynamics.com/data/<EntitySet>` | `CustomerPaymentJournalHeaders`, `CustomerPaymentJournalLines`, `CustomersV3`; company in the `dataAreaId` field; `?cross-company=true` to read across companies | A **custom service** (`POST /api/services/<ServiceGroup>/<Service>/<operation>`) wrapping X++ journal posting, or the Data Management (DMF) package API for batches. Standard OData entities create/read rows; they do not post. |
| **Business Central** | `https://api.businesscentral.dynamics.com/v2.0/<tenant>/<environment>/api/v2.0/companies(<id>)/...` | `customerPaymentJournals`, `customerPayments` (navigable from the journal), `customers`, `salesInvoices` | Varies: bound actions such as `Microsoft.NAV.post` exist on some resources (e.g. general `journals`); for customer payment journals check `$metadata` or use a custom API page / codeunit published as a web service. |
| **Dataverse** (D365 Sales / Customer Service, Power Platform) | `https://<org>.crm.dynamics.com/api/data/v9.2/<entitysetname>` | custom tables, `accounts`, `invoices` | Custom actions / Custom APIs. |

Entity, action and field names differ by version and customisation. **The
source of truth is the environment's `$metadata`** (`GET <base>/data/$metadata`
for F&O) and the app's own client code. The pack's stubs use F&O-style names;
rename them to what your app actually calls. Treat the custom-service path
`/api/services/ARIntegrationServices/ARPostingService/postJournal` as a
placeholder for your real one — Microsoft does not publish a standard
"post customer payment journal" OData action for F&O.

## 2. Entra ID specifics

- Token endpoint: `POST https://login.microsoftonline.com/<tenant>/oauth2/v2.0/token`
  with form fields `grant_type=client_credentials`, `client_id`,
  `client_secret`, `scope=<D365 environment URL>/.default`; response
  `{"token_type":"Bearer","expires_in":3599,"ext_expires_in":3599,"access_token":"..."}`.
  The pack's default (`wiremock-d365/mappings/entra_token.json`) matches any
  tenant path segment.
- Failure codes worth a scenario each: `AADSTS7000222` (client secret expired),
  `AADSTS7000215` (invalid secret), `AADSTS700016` (application not found in
  tenant). Copy the full bodies from your logs.
- MSAL / Azure.Identity: make the authority (`authority`, `AuthorityHost`)
  configurable. MSAL may call instance-discovery and
  `.well-known/openid-configuration` endpoints first; record and stub them, or
  use a plain HTTP token request for the confidential-client flow.
- A 200 token does not mean D365 will accept it: the Entra app must also be
  registered as a user in D365 with roles. That failure is a **401/403 from
  D365 itself** (`stubs/fo_unauthorized.json`), distinct from a token failure.

## 3. The pack's stub library

```
wiremock-d365/
├── mappings/                                 boot-time defaults, priority 10
│   ├── entra_token.json                      token always succeeds
│   └── fo_payment_journal_happy_path.json    header, lines, post all succeed
└── stubs/                                    opt-in via mock_stubs, priority 1
    ├── fo_header_throttled_once.json         429 + Retry-After once, then default
    ├── fo_header_throttled_always.json       429 forever
    ├── fo_line_validation_error.json         400 with an F&O OData error body
    ├── fo_post_service_unavailable.json      503 forever
    ├── fo_post_connection_reset.json         TCP reset: outcome unknown
    ├── fo_post_slow.json                     slower than the client timeout
    ├── entra_token_invalid_client.json       expired client secret
    └── fo_unauthorized.json                  401 from D365 itself
```

Defaults require `Authorization: Bearer e2e-token`, so a missing auth header
falls through to "unmatched" and fails the scenario.

## 4. Dynamics failure modes mapped to the generic catalogue

Each row specialises a row of `references/external-services.md` §6. The error
messages are illustrative: copy exact bodies from production logs.

| D365 behaviour | Generic row | Stub | AR-specific assertion |
|---|---|---|---|
| Service protection limits: 429 with `Retry-After` (F&O and Dataverse both throttle per user/app over a time window) | 429 once / forever | `fo_header_throttled_once`, `fo_header_throttled_always` | header/line call counts; receipt `posted` or retryable |
| Line rejected: customer blocked/on hold in D365, invoice already settled, invalid financial dimension, currency or exchange rate not set up, posting profile missing | 400 validation | `fo_line_validation_error` (+ one variant per real message) | no post call; D365 message stored on the receipt; invoices unchanged |
| Period closed in D365 (but open in the app) | 400 validation | variant of the above on the post call | receipt not `posted`; message surfaced |
| Journal locked / in use by another user or batch | 400 or 409 | inline | *Policy*: retry later vs fail; assert it |
| Expired/invalid client secret | 401 identity provider | `entra_token_invalid_client` | zero `/data/` and `/api/services/` calls |
| App user missing or lacking roles in D365 | 401/403 API | `fo_unauthorized` | bounded calls, clear error |
| Optimistic concurrency on update: entities return `@odata.etag`; stale `If-Match` → 412 | 409/412 | inline 412 | re-read once or fail; no silent overwrite |
| Posting service down | 5xx | `fo_post_service_unavailable` | exactly N post attempts; `post_failed` |
| Timeout / reset on the post call | unknown outcome | `fo_post_slow`, `fo_post_connection_reset` | not `posted`, not re-posted blindly; look up by `PaymentReference` or park for reconciliation |
| Header + some lines created, one line rejected | partial operation | stateful stub on lines | no post call; retry does not duplicate lines in the journal |
| Payment reference already exists in D365 | duplicate | inline 400 or a lookup returning a row | linked to existing voucher, no new journal |
| `$batch` changeset fails (if the app uses `$batch`) | partial operation | inline multipart response | changeset treated as atomic |
| 200 but no `Voucher` / renamed field | unexpected success body | inline 200 | not marked `posted` with a null voucher |

F&O OData error bodies have the shape
`{"error": {"code": "", "message": "...", "innererror": {"message": "...", "type": "..."}}}`;
the useful text (often an Infolog message) is usually in `message`. Dataverse
stopped returning `innererror` in production, so do not make the app depend on
it.

## 5. Asserting a Dynamics posting

```yaml
then:
  mock_requests:
    - method: POST
      url_path: /data/CustomerPaymentJournalLines
      count: 1
      json: {dataAreaId: usmf, AccountType: Cust, AccountDisplayValue: C001, MarkedInvoice: INV-1001,
             CreditAmount: 1000, CurrencyCode: USD, TransDate: "2026-03-20", PaymentReference: R-0101}
  mock_sequence: [POST /data/CustomerPaymentJournalHeaders, POST /data/CustomerPaymentJournalLines, POST /api/services/*/postJournal]
```

- **Company** (`dataAreaId`) on every call in multi-entity setups.
- **Side**: `CreditAmount` for a customer payment; a swapped side is silent.
- **`TransDate`** against the scenario clock and the entity's time zone.
- **On-account remainder**: a line without `MarkedInvoice` for unapplied cash.

## 6. Recording and contract checks against a D365 sandbox

- Record against a UAT/sandbox environment only:
  `--proxy-all "https://<env>.sandbox.operations.dynamics.com" --record-mappings`
  (mechanics in `references/external-services.md` §9). Strip bearer tokens,
  tenant ids, and customer data; keep error bodies verbatim.
- Nightly contract job: fetch `<base>/data/$metadata`, extract the entity sets,
  properties and actions the app uses, diff against a committed snapshot; then
  create one journal header + line with the payload the scenarios assert, read
  it back, delete it. D365 service updates and customisations are the usual
  cause of drift.
