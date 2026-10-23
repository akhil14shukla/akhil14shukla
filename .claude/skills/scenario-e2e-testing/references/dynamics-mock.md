# Faking Microsoft Dynamics 365 (and Entra ID) with WireMock

Read this when pointing the app at the fake, writing stubs for Dynamics
behaviour, deciding which Dynamics failure modes to cover, or keeping the fake
honest against the real API. The ready-made stub library is
`assets/wiremock-d365/` (defaults in `mappings/`, failure modes in `stubs/`).

## Contents

1. Which Dynamics? Identify the API first
2. Making the app reachable for the fake
3. How the stub library is organised
4. WireMock essentials used here
5. Failure-mode catalogue: what to stub and what to assert
6. Asserting what the app sent
7. Recording realistic responses from a sandbox
8. Keeping the fake honest: the nightly contract job

## 1. Which Dynamics? Identify the API first

"Microsoft Dynamics" is several products with different APIs. Find which one
the app calls (grep the client code for the base URL and paths) before writing
any stub.

| Product | Base URL shape | Typical AR objects | How posting is usually done |
|---|---|---|---|
| **Finance & Operations** (D365 Finance, "F&O", formerly AX) | `https://<env>.operations.dynamics.com/data/<EntitySet>` | `CustomerPaymentJournalHeaders`, `CustomerPaymentJournalLines`, `CustomersV3`, `FreeTextInvoiceHeaders`; company in the `dataAreaId` field; `?cross-company=true` to read across companies | A **custom service** (`POST /api/services/<ServiceGroup>/<Service>/<operation>`) wrapping X++ journal posting, or the Data Management (DMF) package API for batches. Standard OData entities create/read rows; they do not post. |
| **Business Central** | `https://api.businesscentral.dynamics.com/v2.0/<tenant>/<environment>/api/v2.0/companies(<id>)/...` | `customerPaymentJournals`, `customerPayments` (navigable from the journal), `customers`, `salesInvoices` | Varies: bound actions such as `Microsoft.NAV.post` exist on some resources (e.g. general `journals`); for customer payment journals check `$metadata` or use a custom API page / codeunit published as a web service. |
| **Dataverse** (Dynamics 365 Sales/Customer Service, Power Platform) | `https://<org>.crm.dynamics.com/api/data/v9.2/<entitysetname>` | custom tables, `accounts`, `invoices` | Custom actions / Custom APIs. |

All three use OAuth 2.0 client credentials against Entra ID (Azure AD):
`POST https://login.microsoftonline.com/<tenant>/oauth2/v2.0/token` with form
fields `grant_type=client_credentials`, `client_id`, `client_secret`,
`scope=<resource>/.default`; response
`{"token_type":"Bearer","expires_in":3599,"access_token":"..."}`.

Entity names, action names and field names differ by version and
customisation. **The source of truth is the environment's `$metadata`**
(`GET <base>/data/$metadata` for F&O) and the app's own client code. The stub
library uses F&O-style names; rename paths and fields to what your app actually
calls, and treat the custom-service path
`/api/services/ARIntegrationServices/ARPostingService/postJournal` as a
placeholder for your real one.

## 2. Making the app reachable for the fake

The app must take both endpoints from configuration:

| Setting | Production | E2E |
|---|---|---|
| Dynamics base URL | `https://contoso.operations.dynamics.com` | `http://wiremock:8080` |
| Entra authority / token URL | `https://login.microsoftonline.com/<tenant>/oauth2/v2.0/token` | `http://wiremock:8080/<tenant>/oauth2/v2.0/token` |
| Client id / secret | from a vault | any non-empty value |
| HTTP timeout, retry count, max back-off | production values | same counts, back-off capped low (e.g. 50 ms) |

Common blockers and fixes:

- **Authority hard-coded** in MSAL/Azure.Identity setup: make it a config
  value. MSAL may also call instance discovery /
  `.well-known/openid-configuration` endpoints; either stub them (copy the
  shapes from a recording, §7) or, for confidential-client flows, use a plain
  HTTP token request in the app's client — it is simpler and testable.
- **HTTPS required** by the client: run WireMock with `--https-port 8443` and
  make the app trust its certificate in e2e mode, or allow `http` when
  `E2E_TEST_HOOKS=1`.
- **Token cache** survives across scenarios and hides token failures: clear it
  through the `/__test/reset-caches` hook, or cache per process only when not in
  e2e mode.
- **An SDK** (Dataverse `ServiceClient`, a generated OData client) still speaks
  HTTP: point its base URL at WireMock.

## 3. How the stub library is organised

```
assets/wiremock-d365/
├── mappings/                      loaded by WireMock at boot; priority 10 (low)
│   ├── entra_token.json           token endpoint always succeeds
│   └── fo_payment_journal_happy_path.json   header, lines, post all succeed
└── stubs/                         opted into per scenario; priority 1 (wins)
    ├── fo_header_throttled_once.json        429 + Retry-After once, then default
    ├── fo_header_throttled_always.json      429 forever
    ├── fo_line_validation_error.json        400 with an OData error body
    ├── fo_post_service_unavailable.json     503 forever
    ├── fo_post_connection_reset.json        TCP reset: outcome unknown
    ├── fo_post_slow.json                    response slower than client timeout
    ├── entra_token_invalid_client.json      expired client secret
    └── fo_unauthorized.json                 401 from D365 itself
```

The runner calls `POST /__admin/reset` before every scenario, which restores
exactly the boot-time mappings and clears the request journal; scenario stubs
never leak into the next scenario.

Defaults are the happy path so a scenario only declares what is *different*
about Dynamics in its case. Defaults require `Authorization: Bearer e2e-token`,
so a missing or wrong auth header falls through to "unmatched" and fails the
scenario.

## 4. WireMock essentials used here

- **Priority**: lower number wins. Defaults use 10, scenario stubs 1.
- **Stateful sequences** (`scenarioName`, `requiredScenarioState`,
  `newScenarioState`): "fail the first call, succeed the second". All state
  machines start in `Started` and are reset by the runner.
- **Faults**: `"fault": "CONNECTION_RESET_BY_PEER" | "EMPTY_RESPONSE" |
  "MALFORMED_RESPONSE_CHUNK" | "RANDOM_DATA_THEN_CLOSE"`.
- **Delays**: `"fixedDelayMilliseconds": 15000` (or `delayDistribution`). Set
  the app's e2e client timeout low (e.g. 2 s) so timeout scenarios stay fast.
- **Response templating** to echo request values (e.g. the journal number the
  app sent):

  ```json
  "response": {
    "status": 201,
    "transformers": ["response-template"],
    "jsonBody": {"JournalBatchNumber": "{{jsonPath request.body '$.JournalBatchNumber'}}", "LineNumber": 1}
  }
  ```

  Put templates in `jsonBody` string values. In a raw `body` string, a template
  directly followed by the JSON's closing brace produces `}}}`, which
  Handlebars rejects with a 500.
- **Request matching on body**: `"bodyPatterns": [{"matchesJsonPath": "$[?(@.CurrencyCode == 'EUR')]"}]`
  makes a stub fire only for a specific payload (e.g. reject EUR lines only).
- **Admin API** used by the runner: `POST /__admin/reset`,
  `POST /__admin/scenarios/reset`, `POST /__admin/mappings`,
  `GET /__admin/requests`, `GET /__admin/requests/unmatched`,
  `GET /__admin/health`. Browse `http://localhost:8080/__admin/requests` while
  debugging a scenario locally.

## 5. Failure-mode catalogue: what to stub and what to assert

Each row is at least one scenario. "Assert" lists what the scenario's `then`
must pin down. Copy exact error bodies from your production logs into the
stubs; the messages below are illustrative.

| Dynamics behaviour | Stub | The app must | Assert |
|---|---|---|---|
| Happy path | defaults | post once, store journal + voucher | payloads (account, amount, currency, date, invoice ref, company), call order, receipt `posted` |
| 429 once, `Retry-After` | `fo_header_throttled_once` | wait as told, retry, succeed | 2 calls to the throttled endpoint, 1 post, `posted` |
| 429 forever | `fo_header_throttled_always` | stop after N attempts, keep receipt retryable | exactly N calls, status `post_failed` (or `queued_for_retry`), no post call |
| 400 validation (customer blocked in D365, invoice already settled, dimension invalid, currency/exchange rate missing, period closed in D365) | `fo_line_validation_error`, variants | not retry; surface D365's message to the user | 1 call, no post call, error text stored, other tables unchanged |
| 401 from Entra (expired/invalid secret: AADSTS7000222 / AADSTS7000215) | `entra_token_invalid_client` | fail fast, alert-worthy error, no data calls | 0 `/data/` calls |
| 401/403 from D365 (app user missing/disabled, missing role) | `fo_unauthorized` | not retry endlessly | bounded calls, clear error |
| 404 on a referenced entity (customer or invoice not in D365) | inline 404 | mark as data error, not transient | no retry, error stored |
| 409/412 ETag conflict on update | inline 412 | re-read and retry once, or fail clearly | call count, final state |
| 500 / 502 / 503 / 504 | `fo_post_service_unavailable` | retry with back-off up to the limit | exact attempt count, final status |
| Timeout (slow response) | `fo_post_slow` | treat outcome as **unknown** | receipt not `posted`, not blindly re-posted; flagged for reconciliation |
| Connection reset after send | `fo_post_connection_reset` | treat outcome as **unknown** | same as timeout |
| Failure part-way (header + 2 of 3 lines created, line 3 rejected) | stateful stub on lines | not post a partial journal; clean up or resume idempotently | no post call; on retry, no duplicate lines (count lines per journal) |
| Duplicate: D365 already has this payment reference (re-delivery, previous unknown outcome) | header/line returns 400 duplicate, or a lookup returns an existing row | detect and link, not post twice | 0 new journals, receipt linked to existing voucher |
| Success with unexpected body (missing `Voucher`, extra fields, different casing) | inline 200 | fail safely, not mark posted with null voucher | status, error |
| Token expires mid-batch | stateful token stub returning a short `expires_in`, data stub 401 once | refresh token once and continue | 2 token calls, all lines posted once |
| `$batch` changeset partially fails (if the app uses `$batch`) | inline multipart response | treat the changeset as atomic | per-line status |

The dangerous class is **unknown outcome** (timeouts, resets after send). A
naive retry double-posts cash. The correct behaviour (look up by an idempotency
key such as the receipt number in `PaymentReference` before re-posting, or park
for reconciliation) must have a scenario, because nothing else will catch its
absence before production does.

## 6. Asserting what the app sent

The journal is the strongest evidence a scenario has. For every posting
scenario:

```yaml
then:
  erp_requests:
    - method: POST
      url_path: /data/CustomerPaymentJournalLines
      count: 1
      json: {dataAreaId: usmf, AccountType: Cust, AccountDisplayValue: C001, MarkedInvoice: INV-1001,
             CreditAmount: 1000, CurrencyCode: USD, TransDate: "2026-03-20", PaymentReference: R-0101}
  erp_sequence: [POST /data/CustomerPaymentJournalHeaders, POST /data/CustomerPaymentJournalLines, POST /api/services/*/postJournal]
```

- Assert **company** (`dataAreaId`) on multi-entity setups; posting to the
  wrong legal entity is a silent, expensive bug.
- Assert **amount sign and side** (`CreditAmount` vs `DebitAmount`).
- Assert **dates** against the scenario clock (posting date is a business date).
- Every scenario that must not reach Dynamics asserts
  `{url_path_pattern: ".*", count: 0}`.

## 7. Recording realistic responses from a sandbox

Hand-written stubs drift from reality. Capture real shapes once, from a
non-production environment, then curate:

```bash
java -jar wiremock-standalone.jar --port 8080 --root-dir rec \
     --proxy-all "https://contoso-uat.sandbox.operations.dynamics.com" --record-mappings
# point a local app run at http://localhost:8080 and exercise the flows, then stop WireMock
```

or start/stop a recording through the admin API
(`POST /__admin/recordings/start {"targetBaseUrl": "..."}`,
`POST /__admin/recordings/stop`). Afterwards:

- **Strip** `Authorization` headers, tokens, tenant ids, and any real customer
  data from the recorded files.
- **Generalise** request matchers (exact body matches are too strict; match on
  method + path, and on `matchesJsonPath` only where behaviour differs).
- Keep recorded **error** bodies verbatim — they are the most valuable part.

## 8. Keeping the fake honest: the nightly contract job

The fake encodes assumptions about Dynamics. When Microsoft ships an update or
someone customises an entity, the assumptions can silently go stale. Guard with
a scheduled (not per-PR) job against a dedicated sandbox:

1. Fetch `$metadata` and diff the entity sets, fields, and actions the app uses
   against a committed snapshot. A removed or renamed field fails the job.
2. Run a handful of contract checks: create a journal header and line with the
   same payload the scenarios assert, read them back, delete them. The
   assertion is that the real API accepts exactly what the fake accepts.
3. On failure, open an issue; do not block PRs on sandbox availability.
