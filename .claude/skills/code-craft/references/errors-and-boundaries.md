# Errors, boundaries, and failure at the edges

Read this when writing error handling, validating input at a system boundary,
or adding retries, timeouts, or idempotency to a network call.

Most production incidents are not "the logic was wrong". They are "something
outside the process behaved differently than assumed, and nothing handled it."
This file covers the patterns for that.

## The standing rules

The reader at 2am is almost always chasing an error. What you write here
determines whether they find the cause in one minute or one hour.

- **Distinguish expected from exceptional.** "User not found" during a lookup
  is an ordinary outcome — model it in the return type (`Option`, `Result`,
  null with a documented contract, a sentinel error). "Database connection
  refused" is exceptional — throw/return an error and let it travel. Using
  exceptions for ordinary control flow hides real failures in the noise.
- **Fail fast at the boundary, not deep inside.** Validate input where it
  enters the system — the HTTP handler, the CLI parser, the queue consumer —
  and pass validated types inward. Then internal functions do not each need
  defensive checks, and a bad value cannot travel three layers before
  surfacing somewhere unrelated.
- **Every error message answers three questions**: what operation failed, on
  what input, and what the caller should do. `"invalid config"` fails all
  three. `"config: retry_limit must be >= 0, got -1 (config.yaml line 14)"`
  answers all three. Include the offending value — but never secrets, tokens,
  full credit-card numbers, or personal data.
- **Add context as the error travels up; do not replace it.** Wrap with the
  operation you were attempting and preserve the cause (`%w` in Go,
  `raise ... from e` in Python, `cause` in JS `Error`, exception chaining in
  Java). A stack of `"charge order 55: fetch customer: connection refused"`
  locates the bug immediately; a bare `"connection refused"` does not.
- **Never catch broadly to keep going.** `catch (e) {}` and `except Exception:
  pass` convert a loud bug into a silent wrong answer, which is strictly worse.
  Catch the specific type you can actually handle.
- **Do not log and rethrow.** You get the same failure printed five times and
  no clearer picture. Log where you handle it; wrap and return everywhere else.
- **Clean up deterministically.** Use the language's scoped mechanism —
  `defer`, `try-with-resources`, `using`, RAII, `finally` — not manual cleanup
  on each return path, because someone will add a sixth return and miss it.

---

## The three-layer error model

Classify every failure into one of three buckets, because each needs different
handling. Mixing them is what produces both silent data loss and pager noise.

| Class | Example | Handling |
|---|---|---|
| **Expected outcome** | user not found, empty result, cache miss | Model in the return type. Not an exception. No log at error level. |
| **Caller's fault** | malformed input, missing field, bad enum value | Reject at the boundary with a message naming the field and the constraint. 4xx. Do not page anyone. |
| **Our fault or the world's** | DB down, disk full, nil deref, timeout | Propagate with context, log at error, alert. 5xx. |

The bug that matters: a "caller's fault" being reported as a 500 wakes someone
at night for a client typo, and an "our fault" reported as a 400 hides an
outage. Getting the classification right is worth more than any amount of
retry logic.

## Validate once, at the boundary

Every system has a small number of places where untrusted data enters: HTTP
handlers, CLI argument parsing, queue consumers, file/CSV importers, webhook
receivers, and anything reading the environment or a config file.

Validate there, convert into a type that *cannot* be invalid, and pass that type
inward. The payoff: internal functions stop being littered with defensive checks
and stop disagreeing about what "valid" means.

```ts
// Boundary: parse, don't validate. After this line, the rest of the codebase
// works with a type that is correct by construction.
const CreateOrder = z.object({
  customerId: z.string().uuid(),
  items: z.array(z.object({ sku: z.string().min(1), qty: z.number().int().positive() })).min(1),
  currency: z.enum(["USD", "EUR", "GBP"]),
});

const parsed = CreateOrder.safeParse(await req.json());
if (!parsed.success) {
  return respond(400, { error: "invalid_request", details: parsed.error.issues });
}
await placeOrder(parsed.data);   // placeOrder never checks any of this again
```

What to validate: presence, type, range/length, format, enum membership, and
cross-field rules (`endDate > startDate`). What *not* to do: trust a field
because the frontend also validates it. The frontend is not a security boundary.

## Writing an error message someone can act on

A good message contains the operation, the identifying input, the constraint
violated, and the observed value:

```
config: retry_limit must be >= 0, got -1 (config.yaml line 14)
charge order 4471: stripe: card_declined (insufficient_funds)
import row 232: column "shipped_at" expected ISO-8601 date, got "12/03/25"
```

Never include: passwords, tokens, API keys, session cookies, full card numbers,
or personal data. If you must reference a secret, reference its *name*
(`AWS_SECRET_ACCESS_KEY is not set`), never its value.

Also avoid the message that names the internal implementation rather than the
user's problem — `NullPointerException in OrderMapper.line 88` tells the
operator nothing about what to do.

## Error taxonomies

Define one error type per module or crate, rooted so a caller can catch the
whole family or one specific case:

```py
class PaymentError(Exception): ...              # catch the family
class CardDeclined(PaymentError): ...           # catch the specific case
class GatewayUnavailable(PaymentError): ...     # retryable
```

Attach the data a handler needs (the order id, the retry-after, whether it is
retryable) as fields, not by parsing the message string. Message parsing breaks
the first time someone improves the wording.

## Retries, timeouts, and idempotency — the three that travel together

Every network call needs all three decided together. Choosing one without the
others is where cascading failures come from.

- **Timeout**: no unbounded waits, ever. Set it from the caller's budget: if
  your endpoint must answer in 2s and makes three calls, they cannot each have a
  2s timeout. Propagate a deadline (context/cancellation token) rather than
  hardcoding per-call values.
- **Retry only what is safe and transient.** Retry: timeouts, connection resets,
  429, 502/503/504. Do not retry: 400, 401, 403, 404, 422 — the answer will not
  change, and you have turned a client bug into a load test.
- **Exponential backoff with jitter.** Fixed-interval retries from many clients
  synchronise into a thundering herd that keeps a recovering service down.
  `delay = min(base * 2^attempt, cap) * random(0.5, 1.5)`.
- **Cap total attempts and total elapsed time**, not just attempts.
- **Idempotency**: anything retried must be safe to run twice. Send an
  idempotency key on writes; make the receiver deduplicate on it. Without this,
  a retried payment is a double charge.
- **Circuit breaking**: after N consecutive failures, stop calling for a cooling
  period and fail fast. Retrying into a dead dependency converts its outage into
  yours.

## Partial failure

When processing a batch, decide explicitly — and say so in the API — whether it
is all-or-nothing or best-effort. Silently succeeding on 97 of 100 rows and
returning 200 is the worst option, because nobody learns about the three.

```
{ "processed": 97, "failed": 3,
  "failures": [{ "row": 12, "error": "sku not found: ABC-9" }, ...] }
```

## Resource cleanup on the failure path

The happy path rarely leaks. The error path does — a return added later that
skips the close. Use the scoped construct every time so the compiler or runtime
handles it: `defer` (Go), `try-with-resources` (Java), `using` (C#), `with`
(Python), RAII (Rust/C++), `try/finally` (JS). Never hand-write cleanup at each
return.

Especially: database transactions (roll back on any error path), file handles,
locks (release even when the guarded code throws), and subscriptions/listeners.

## Failing safely

When you cannot complete the operation, decide what state the system is left in
and make it explicit:

- **Fail closed** for anything security- or money-related: if the permission
  check errors, deny; if the fraud check times out, do not charge.
- **Fail open** for enrichment that is not load-bearing: if the recommendation
  service is down, render the page without recommendations.

Write down which one you chose in a comment. Reviewers cannot infer it, and the
wrong default is invisible until it matters.
