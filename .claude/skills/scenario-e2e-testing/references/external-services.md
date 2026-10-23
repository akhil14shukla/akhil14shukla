# Faking external HTTP systems with WireMock

Read this when pointing the app at a fake for any external HTTP system (ERP,
payment provider, CRM, tax service, bank API), writing its stubs, deciding which
of its failure modes to cover, or keeping the fake honest against the real API.
System-specific packs (e.g. Microsoft Dynamics 365) live under `use-cases/` and
build on this file.

## Contents

1. Identify the API before writing a stub
2. Making the app reachable for the fake
3. Organising stubs: defaults and opt-in failure modes
4. WireMock essentials
5. Faking the identity provider
6. Generic failure-mode catalogue
7. The unknown-outcome rule
8. Asserting what the app sent
9. Recording, and the nightly contract job
10. Writing a new use-case pack

## 1. Identify the API before writing a stub

From the app's client code (not documentation alone), list for each external
system: base URL config key, auth scheme, every method + path the app calls, the
request fields it sends, the response fields it reads, and its retry/timeout
policy. Where the vendor publishes a machine-readable contract (OpenAPI,
OData `$metadata`, WSDL), check the list against it. That list is the stub
inventory; anything the app calls that is not on it shows up as an unmatched
request and fails the scenario.

## 2. Making the app reachable for the fake

The app must take every endpoint from configuration:

| Setting | Production | E2E |
|---|---|---|
| API base URL | vendor URL | `http://wiremock:8080` (path prefix per system if several) |
| Token / authority URL | identity provider | `http://wiremock:8080/<path>` |
| Client id / secret / API key | from a vault | any non-empty value |
| HTTP timeout, retry count, max back-off | production values | same counts, back-off capped low (e.g. 50 ms), timeout low (e.g. 2 s) |

Common blockers:

- **Hard-coded authority or base URL** inside an SDK setup: make it config.
- **HTTPS required** by the client: run WireMock with `--https-port 8443` and
  trust its certificate in e2e mode, or allow `http` only when
  `E2E_TEST_HOOKS=1`.
- **Token cache** survives across scenarios and hides token failures: clear it
  via `/__test/reset-caches`.
- **An SDK** still speaks HTTP: point its base URL at WireMock. If it insists on
  discovery endpoints (OpenID configuration, instance discovery), record and
  stub them (§9).
- **Several systems** on one WireMock: give each a path prefix
  (`/erp/...`, `/payments/...`) or run one WireMock per system on its own port.

## 3. Organising stubs: defaults and opt-in failure modes

```
e2e/wiremock/
├── mappings/<system>/   loaded by WireMock at boot, priority 10 (low): token + happy path
└── stubs/<system>/      opted into per scenario via mock_stubs, priority 1 (wins)
```

The runner calls `POST /__admin/reset` before every scenario, which restores
exactly the boot-time mappings and clears the request journal, so scenario
stubs never leak into the next scenario. Defaults are the happy path so a
scenario declares only what is *different* about the external system in its
case. Make defaults require the auth header the app should send
(`"headers": {"Authorization": {"equalTo": "Bearer e2e-token"}}`), so a missing
or wrong header falls through to "unmatched" and fails the scenario.

Name stub files `<system>_<endpoint>_<behaviour>.json`, e.g.
`payments_charge_declined.json`, `erp_post_service_unavailable.json`.

## 4. WireMock essentials

- **Priority**: lower number wins. Defaults use 10, scenario stubs 1.
- **Stateful sequences** (`scenarioName`, `requiredScenarioState`,
  `newScenarioState`): "fail the first call, succeed the second". All state
  machines start in `Started` and are reset by the runner.

  ```json
  {"priority": 1, "scenarioName": "throttle", "requiredScenarioState": "Started", "newScenarioState": "once",
   "request": {"method": "POST", "urlPath": "/v1/charges"},
   "response": {"status": 429, "headers": {"Retry-After": "0"}}}
  ```

  After the first call the state is `once`, this stub no longer matches, and the
  default happy-path stub answers.
- **Faults**: `"fault": "CONNECTION_RESET_BY_PEER" | "EMPTY_RESPONSE" |
  "MALFORMED_RESPONSE_CHUNK" | "RANDOM_DATA_THEN_CLOSE"`.
- **Delays**: `"fixedDelayMilliseconds": 15000` (or `delayDistribution`).
- **Response templating** to echo request values:

  ```json
  "response": {"status": 201, "transformers": ["response-template"],
               "jsonBody": {"id": "{{jsonPath request.body '$.reference'}}", "status": "created"}}
  ```

  Put templates in `jsonBody` string values. In a raw `body` string, a template
  directly followed by the JSON's closing brace produces `}}}`, which
  Handlebars rejects with a 500 (verified on WireMock 3.13).
- **Body-specific stubs**: `"bodyPatterns": [{"matchesJsonPath": "$[?(@.currency == 'EUR')]"}]`
  fires only for a specific payload (reject EUR only).
- **Admin API** used by the runner: `POST /__admin/reset`,
  `POST /__admin/scenarios/reset`, `POST /__admin/mappings`,
  `GET /__admin/requests`, `GET /__admin/requests/unmatched`,
  `GET /__admin/health`. Browse `http://localhost:8080/__admin/requests` while
  debugging a scenario locally.

## 5. Faking the identity provider

Most business APIs sit behind OAuth 2.0. Fake the token endpoint too, so the
app's real token acquisition, caching and refresh run:

- **Default mapping**: `POST <token path>` with
  `grant_type=client_credentials` in the body → `200` with
  `{"token_type": "Bearer", "expires_in": 3599, "access_token": "e2e-token"}`.
- **Failure stubs**: `401 invalid_client` (expired or rotated secret), `400
  invalid_scope`, a 5xx, a slow response.
- **Expiry mid-run**: a token response with a short `expires_in` plus a data
  stub that returns 401 once (stateful) — the app must refresh once and continue
  without duplicating work.

## 6. Generic failure-mode catalogue

Each row is at least one scenario per integration call that changes state in the
external system. "Assert" lists what `then` must pin down. Copy exact error
bodies from production logs into the stubs.

| External behaviour | Stub | The app must | Assert |
|---|---|---|---|
| Happy path | defaults | call once, store the external id/reference | payloads, call order, local status |
| 429 once with `Retry-After` | stateful | wait as told, retry, succeed | 2 calls, 1 success, final status |
| 429 forever | priority-1 429 | stop after N attempts, stay retryable | exactly N calls, retryable failure status |
| 400/422 validation (business rule rejected) | 4xx with real error body | not retry; surface the system's message | 1 call, error stored, other tables unchanged |
| 401 from identity provider | token stub 401 | fail fast, no business calls | 0 business calls |
| 401/403 from the API (permissions) | 401/403 | bounded attempts, clear error | call count, error |
| 404 on a referenced entity | 404 | treat as a data error, not transient | no retry |
| 409/412 conflict (ETag / version) | 409/412 | re-read and retry once, or fail clearly | call count, final state |
| 500/502/503/504 | 5xx | retry with back-off up to the limit | exact attempt count, final status |
| Timeout (slow response) | `fixedDelayMilliseconds` > client timeout | treat outcome as **unknown** (§7) | not marked done, not blindly re-sent |
| Connection reset after send | `fault` | treat outcome as **unknown** | same as timeout |
| Partial multi-call operation (step 3 of 4 fails) | stateful / per-path stubs | not commit a partial result; retry without duplicates | no final call; on retry, no duplicate creates |
| Duplicate: the system already has this reference | 4xx duplicate, or lookup returns existing | detect and link, not create twice | 0 new creates, local row linked |
| Success with an unexpected body (missing id, new fields, casing) | 2xx inline | fail safely, not mark done with null id | status, error |
| Token expires mid-batch | §5 | refresh once, continue | 2 token calls, no duplicates |

## 7. The unknown-outcome rule

After a timeout or a reset *after the request was sent*, the app does not know
whether the external system acted. A naive retry duplicates the effect: money
moves twice, an order ships twice. The correct behaviour — look up by an
idempotency key before re-sending, send an idempotency header the system
honours, or park for reconciliation — must have scenarios, because nothing else
will catch its absence before production does.

## 8. Asserting what the app sent

The journal is the strongest evidence a scenario has. For every call that
changes external state, assert the fields that carry business meaning: tenant
or company, account/customer, amount and its sign or side, currency, business
date, the reference that links back to the local row.

```yaml
then:
  mock_requests:
    - {method: POST, url_path: /v1/charges, count: 1, json: {amount: 1999, currency: EUR, order_ref: ORD-0042}}
  mock_sequence: [POST /v1/customers, POST /v1/charges]
```

Every scenario that must not reach the system asserts
`{url_path_pattern: ".*", count: 0}` (or a narrower pattern per system).

## 9. Recording, and the nightly contract job

**Recording** captures real shapes from a non-production environment:

```bash
java -jar wiremock-standalone.jar --port 8080 --root-dir rec \
     --proxy-all "https://sandbox.vendor.example" --record-mappings
```

or `POST /__admin/recordings/start {"targetBaseUrl": "..."}` then
`POST /__admin/recordings/stop`. Afterwards strip tokens, auth headers, tenant
ids and real customer data; generalise matchers to method + path (plus
`matchesJsonPath` only where behaviour differs); keep error bodies verbatim.

**The nightly contract job** keeps the fake honest (Fowler's *ContractTest*):
on a schedule, not per PR, against a dedicated sandbox —

1. Diff the vendor's machine-readable contract (OpenAPI / `$metadata`) for the
   endpoints and fields the app uses against a committed snapshot.
2. Send the same payloads the scenarios assert and check the real API accepts
   them and returns the fields the app reads. Check formats, not data values.
3. On failure open an issue to update the fake and the code; do not block PRs on
   sandbox availability.

## 10. Writing a new use-case pack

When an app integrates with a specific system you will test repeatedly, capture
the system-specific knowledge as a pack under `use-cases/<system>-<domain>/`
(structure in `use-cases/README.md`): its API identification table, the
default and failure stubs, its real error catalogue mapped to §6, a domain case
catalogue, the discovery greps, and a runnable example. Keep everything generic
in `references/`.
