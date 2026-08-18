# Anti-pattern catalogue: before and after

Each entry is a construct that reliably makes code hard to read or change, why
it hurts, and the version to write instead. When a reviewer says "this is hard
to follow" and you are not sure why, find the shape here.

## 1. The boolean parameter

```ts
// Before — unreadable at the call site.
createUser(name, email, true, false);

// After — the call site says what it means.
createUser({ name, email, sendWelcomeEmail: true, isAdmin: false });
// or split the function entirely:
createAdminUser({ name, email });
```

Why: a reader of `createUser(name, email, true, false)` must open the definition
to learn anything. Options objects and split functions both keep meaning at the
call site, where the reader is.

## 2. The arrow of nesting

```go
// Before — the actual work is four levels deep and the conditions are
// impossible to hold in your head at once.
func process(o *Order) error {
    if o != nil {
        if o.IsValid() {
            if o.Total > 0 {
                if !o.Paid {
                    return charge(o)
                }
            }
        }
    }
    return nil
}

// After — every precondition is stated once and dismissed; the real work is
// at the bottom, unindented.
func process(o *Order) error {
    if o == nil          { return errors.New("process: nil order") }
    if !o.IsValid()      { return fmt.Errorf("process: order %s invalid", o.ID) }
    if o.Total <= 0      { return nil }   // nothing to charge
    if o.Paid            { return nil }   // already settled
    return charge(o)
}
```

The `return nil` cases now carry a comment explaining *why* nothing happens,
which the nested version could not express at all.

## 3. Swallowing the error

```js
// Before — when this breaks, there is no evidence anywhere.
try { await saveOrder(order); } catch (e) {}

// After — either handle it meaningfully...
try {
  await saveOrder(order);
} catch (err) {
  throw new Error(`saveOrder failed for ${order.id}`, { cause: err });
}

// ...or state explicitly why ignoring is correct.
try {
  await cache.set(key, value);
} catch (err) {
  // Cache writes are best-effort; a failure must not fail the request.
  logger.warn({ err, key }, "cache write failed");
}
```

An empty catch turns a loud failure into a silent wrong answer, which is the
most expensive defect class there is.

## 4. Stringly-typed everything

```ts
// Before — every call site can pass a typo, and nothing catches it.
function setStatus(order: Order, status: string) {}
setStatus(order, "shiped");   // ships nothing, forever

// After — the compiler rejects the typo.
type OrderStatus = "pending" | "paid" | "shipped" | "cancelled";
function setStatus(order: Order, status: OrderStatus) {}
```

The same applies to IDs (`UserId` vs `OrderId` newtypes), units
(`Seconds` vs `Milliseconds`), and any closed set of values.

## 5. The god function

Symptom: 200 lines, six responsibilities, comments acting as section headers,
and a name containing "And" or ending in "Handler".

Fix: each comment-headed block is a function. Name each for its *outcome*, not
its steps. The original becomes an orchestrator you can read in ten seconds:

```py
def handle_signup(request):
    payload   = parse_signup(request)
    validate_signup(payload)
    user      = create_user(payload)
    send_welcome_email(user)
    return signup_response(user)
```

If you cannot name the extracted piece without "Helper", "Utils", or "And", the
seam is wrong — look for a different split.

## 6. Duplicated logic with a subtle drift

Two copies of a rule are not twice the code; they are a guarantee that one of
them will be fixed and the other will not. This is how "we fixed that bug last
month" turns into "it is back."

Rule of thumb: two copies is a note to yourself; three copies is a function.
Extract when the *concept* is the same, not when the *characters* are the same —
identical-looking code that encodes two unrelated rules should stay separate,
because those rules will diverge and the shared function will grow a boolean
parameter (see #1).

## 7. Primitive obsession at boundaries

```java
// Before — nothing stops these being passed in the wrong order.
void transfer(String from, String to, double amount) {}
transfer(amount, fromAccount, toAccount);  // compiles fine, ruins someone's day

// After — wrong order no longer compiles, and money is not a double.
void transfer(AccountId from, AccountId to, Money amount) {}
```

Money as a floating-point number is its own bug: `0.1 + 0.2 != 0.3` in every
IEEE-754 language. Use integer minor units or a decimal type.

## 8. Comments that restate the code

```py
# Before
i = i + 1          # increment i
# loop over users
for user in users: # ...

# After: delete them. Then spend that attention on the comment that matters:
# Stripe caps a single charge at 999999 cents, so invoices above that are split
# across charges. Safe because each line item's payment intent is idempotent.
```

If a comment is needed to explain *what* a line does, rename the identifiers
until it is not.

## 9. Speculative generality

A plugin system with one plugin. An interface with one implementation. A config
option nobody sets. `AbstractBaseFactoryProvider`. Each one costs a layer of
indirection on every read, forever, in exchange for flexibility that usually
never gets used — and when the second case does arrive, it is rarely the shape
you guessed.

Build for the case you have. The second implementation is when you learn what
the abstraction should be.

## 10. Mutable shared state

```js
// Before — order of execution now determines correctness, and tests pass or
// fail depending on the order the test runner happens to pick.
let currentUser = null;
function login(u)   { currentUser = u; }
function canEdit()  { return currentUser?.isAdmin; }

// After — the dependency is visible, and every call is independently testable.
function canEdit(user) { return user.isAdmin; }
```

## 11. Magic numbers and strings

```py
# Before
if user.age >= 18 and retries < 3 and delay > 0.5: ...

# After — named constants say what the number means, and there is now exactly
# one place to change it.
LEGAL_ADULT_AGE   = 18
MAX_RETRIES       = 3
MIN_BACKOFF_SECONDS = 0.5
```

The exception: a number whose meaning is fully carried by context (`x / 2` to
halve, `arr[0]` for the first) does not need a name.

## 12. Returning different shapes from one function

```ts
// Before — no caller can handle this correctly.
function findUser(id): User | null | undefined | never {
  if (!id) throw new Error("bad id");
  if (notFound) return null;
  if (deleted) return undefined;
  return user;
}

// After — one contract, stated in the type.
function findUser(id: UserId): User | null   // null means "no such user"
```

## 13. Fixing the symptom

A null check added where the crash happened, when the real question is why the
value was null three layers up. The check silences the stack trace and moves the
bug somewhere harder to find.

Before adding a defensive check, ask: *should this value ever be absent here?*
If no, fix the producer and let this code assume it. If yes, that is a
legitimate case and belongs in the type.

## 14. Log-and-rethrow

```java
// Before — the same failure appears five times in the logs, at five layers,
// and you still cannot see which one mattered.
catch (IOException e) { log.error("failed", e); throw e; }

// After — add context and propagate; log once, where it is handled.
catch (IOException e) {
    throw new StorageException("read manifest " + path, e);
}
```

## 15. Configuration by mutation at import time

Module-level code that reads the environment, opens connections, or mutates
globals when the file is imported makes import order significant, breaks tests
that import it, and turns a missing environment variable into a crash before
any error handling exists.

Do the work in a function, called explicitly from a composition root
(`main`, the app factory, the DI container).
