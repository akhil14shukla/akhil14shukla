# Scenario format

Read this when writing, reviewing, or debugging a scenario file. The annotated
template with every key is `assets/templates/scenario.template.yaml`; this file
explains the semantics and the authoring rules. Snippets here use a neutral,
illustrative orders domain — replace names with the app's own. Runnable
scenarios exist only inside use-case packs; look at them only if a pack applies
to this app (`use-cases/README.md`).

## Contents

1. Anatomy
2. `given` — the starting state
3. `when` — the steps
4. `then` — the expected end state
5. Matching rules and matchers
6. Variables
7. Authoring rules
8. Reading a failure
9. Drafting expectations with `--capture`

## 1. Anatomy

```yaml
id: ORD-PAY-004
title: Payment provider declines the charge; order stays unpaid with the provider's reason and nothing is shipped
tags: [payment, negative]
clock: 2026-03-20T09:00:00Z
given:   {sql: [...], rows: {...}, mock_stubs: [...]}
when:    [ {request: ..., expect: ..., save: ...}, {wait_for: ...}, ... ]
then:    {db: {...}, db_unchanged: [...], mock_requests: [...], mock_sequence: [...]}
```

`id` is unique and permanent. Use `<SYSTEM>-<AREA>-<NNN>`, one AREA per stage of
the business flow (intake, identification, processing, validation, sending to
the external system, reversal, sync-back) plus `REG` for regressions from
incidents, tagged with the incident id.

## 2. `given` — the starting state

Applied after the reset to "migrated + `base_seed`":

| Key | Meaning |
|---|---|
| `sql` | SQL files (relative to the scenario file), run in order. For row graphs many scenarios share. |
| `rows` | `{table: [row, ...]}` inserted in the order written. Parents before children. `schema.table` works. Dicts/lists become `jsonb`. |
| `mock_stubs` | WireMock mappings layered over the boot-time defaults: `{file: path}` (a mapping or `{"mappings": [...]}`) or `{inline: {...}}`. |
| `clock` (top level) | Sent to the app's clock hook before `when`. Available as `{{clock}}`. |

Rule of thumb: what the scenario is *about* goes inline in `rows`, so a reader
sees it without opening another file; incidental context comes from a fixture.

Explicit ids (`id: 1`) are fine and make child rows readable; the runner
restarts sequences per scenario. Do not mix explicit ids with app-generated
inserts on the same table in one scenario — the sequence does not know about
your explicit id and the app's insert collides. Either let the app create the
row (and `save` its id) or insert it yourself.

## 3. `when` — the steps

| Step | Fields | Notes |
|---|---|---|
| `request` | `method`, `path`, `query`, `headers`, `json` or `body`, `timeout_s` | Base URL and default headers come from config. |
| `expect` | `status`, `json` (subset), `body_contains` | On a status mismatch the remaining checks are skipped and the body is printed. |
| `save` | `{var: $.json.path}` | Minimal JSONPath: `$.a.b[0].c`. |
| `wait_for` | `sql`, `equals`, `timeout_s`, `interval_s` | Polls the first column of the first row. For async workers. |
| `sql` | a SQL string | Change state mid-scenario: a concurrent user, a manual fix, a period closing. |
| `mock_stubs` | list as in `given` | Change external behaviour mid-scenario: outage begins, outage ends. |
| `set` | `{var: value}` | Name a literal for reuse in `then`. |

A step may set `continue_on_failure: true` to keep going after its failure
(rarely useful; the first failure usually explains the rest).

Typical multi-step shapes:

- **Full flow**: create → process → send. One scenario per end-to-end happy
  path; edge cases start from the state just before the step under test.
- **Retry after fix**: send (external system rejects) → `mock_stubs` (system
  fixed) → send again → assert exactly one accepted call and the error cleared.
- **Idempotency**: send → send again → assert the second is refused and the
  journal shows one outbound call.

## 4. `then` — the expected end state

### `db`

```yaml
db:
  orders:
    mode: exact          # exact (default) | contains | absent
    where: "customer_no = 'C001'"
    order_by: order_no   # optional; makes comparison positional
    count: 2             # optional; with or without rows
    rows: [...]
```

- `exact`: the filtered table holds these rows and no others. Order-insensitive
  (a one-to-one assignment is found) unless `order_by` is given.
- `contains`: each listed row matches a distinct actual row; others may exist.
- `absent`: no actual row matches any listed row.
- Each row is a **subset**: only the listed columns are compared.

### `db_unchanged`

`[table, ...]` — full contents before `when` and after must be identical,
ignoring `snapshot.ignore_columns`. This is the cheapest strong assertion in the
suite: "validation failed, so *nothing* moved." Use it on every negative path.

### `mock_requests`

```yaml
mock_requests:
  - {method: POST, url_path: /v1/charges, count: 1, json: {amount: 1999, currency: EUR, order_ref: ORD-0042}}
  - {url_path_pattern: "/v1/shipments", count: 0}
  - {method: POST, url_path: /v1/refunds, body_contains: "ORD-0042"}   # no count: at least one
```

Filters combine with AND: `method`, `url_path` (exact path, no query string),
`url_path_pattern` (regex), `body_contains`, `json` (subset of the parsed body).
`count` is exact. To say "no external system was called at all":
`{url_path_pattern: ".*", count: 0}`.

### `mock_sequence`

`["POST /v1/customers", "POST /v1/charges", "POST /v1/*/capture"]` — these calls
happened in this relative order (glob patterns; other calls may interleave).
Use it where order is the rule: create before update, all parts before commit.

### `mock_unmatched`

Default `none`: if the app called a URL that no stub matched, the scenario
fails and lists the calls. This catches new, untested integrations. Set
`allow` only with a comment saying why.

## 5. Matching rules and matchers

| Expected | Actual passes when |
|---|---|
| object | every listed key exists and matches; extra keys ignored |
| list | same length, element-wise match |
| number or numeric string | equal as decimals: `1000`, `"1000.00"`, `Decimal('1000.00')` all match |
| ISO timestamp with time | same instant: `2026-03-20T09:00:00Z` matches `2026-03-20 09:00:00+00` |
| date | ISO string equality: `2026-03-20` |
| `null` | actual is null |
| other string | string equality |

Matchers (a whole string value):

| Matcher | Passes when |
|---|---|
| `"{{any}}"` | always |
| `"{{not_null}}"` | not null |
| `"{{uuid}}"` | canonical UUID |
| `"{{iso_datetime}}"` | parses as an ISO timestamp |
| `"{{regex:PATTERN}}"` | `re.search` finds PATTERN |
| `"{{contains:TEXT}}"` | TEXT is a substring |
| `"{{gt:N}}"` / `"{{lt:N}}"` | numeric comparison |

Prefer literals. A matcher is for values that are genuinely not knowable
(generated ids, timestamps from a column default); every matcher where a literal
was possible is a weaker test.

## 6. Variables

`{{name}}` is replaced in `given.rows`, `given.mock_stubs`, every step, and
`then`. Built-ins: `scenario_id`, `clock`. Others come from `save` and `set`.
A string that is exactly `"{{name}}"` becomes the raw value (an integer id stays
an integer); inside a longer string it is interpolated as text (paths, SQL).

## 7. Authoring rules

1. **One business rule per scenario.** The title states condition and outcome;
   if it needs "and also", split it.
2. **The expected values are worked out by a human, before running.** If you
   cannot state the right answer, you have found a requirements question — ask
   the business owner, do not let the code decide.
3. **Every negative path asserts that nothing else happened**: `db_unchanged`
   on the affected tables and `count: 0` on external calls that must not occur.
4. **Every scenario that calls an external system asserts the payload** of the
   call that matters — not just that a call happened.
5. **Use boundary values**: one unit inside and one outside a limit; the last
   day of a period and the first of the next.
6. **Copy real error bodies** from production logs into stubs, so the app's
   error parsing is tested against what the external system actually returns.
7. **Regression scenarios cite their origin**: `tags: [regression, INC-2291]`
   and a comment with a one-line summary of what went wrong.
8. **Keep scenarios small**: under ~60 lines. Long scenarios hide the rule.

## 8. Reading a failure

```
[FAIL] ORD-ALLOC-006 Partial stock is reserved from the oldest batch first (0.17s)
       - db.stock_batches[0].reserved: expected 10, got 0
       - db.stock_batches[1].reserved: expected 2, got 12
```

The path says where: `step N` (a response), `db.<table>` (end state),
`mock ...` (external calls; the journal is printed), `db.<table> changed but
must not` (a `db_unchanged` table moved; removed and added rows are printed).
An `ERROR` (not `FAIL`) means the harness could not run the scenario — bad SQL
in a fixture, WireMock unreachable, a foreign-key violation in `given` — and the
message names it. `[SKIP]` lines list quarantined scenarios and their reason.

## 9. Drafting expectations with `--capture`

```bash
uv run e2e/scenario_runner.py --config e2e/e2e.config.yaml run --filter ORD-PAY-007 --capture e2e/out/actual
```

writes `e2e/out/actual/ORD-PAY-007.actual.yaml`: every table in
`snapshot.tables` and every external call observed. Use it to draft a `then`
block or to see the full picture of a failure — then **cut it down to the
columns the rule is about and check each value by hand**. Committing a capture
unread turns the suite into a recording of current behaviour, bugs included.
