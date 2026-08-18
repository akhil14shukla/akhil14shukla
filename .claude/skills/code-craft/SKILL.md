---
name: code-craft
description: Write and edit source code in any language to a standard a stranger can read, trust, and change safely — naming, function shape, error handling, control flow, state, module boundaries, and knowing when to restructure instead of patch. Use this whenever the deliverable is source code in TypeScript, JavaScript, Go, Rust, Java, C#, C++, Ruby, PHP, Kotlin, Swift, shell, or SQL — including "quick" scripts, small edits, and refactors. For Python, use python-engineering instead. Trigger on "implement", "add a feature", "write a function", "refactor", "clean this up", "fix this code", "port this", or any request that ends in a code file changing.
---

# Code craft

## The standard you are writing to

Someone who has never seen this codebase will open your file at 2am with a
production incident open, read one function, and have to decide whether it is
the cause. Everything below serves that moment.

That reader has no context. They cannot ask you anything. They will not read
the whole file — they will read the function they landed on, and maybe one
level up. So each unit of code has to be **locally understandable**: correct to
reason about without holding the rest of the system in your head.

This is not about beauty. Code that reads clearly gets fixed correctly under
pressure; code that reads cleverly gets fixed wrongly. The three failure modes
that actually cause damage, in order:

1. Code whose behaviour differs from what its name and shape suggest.
2. Code that silently does nothing when it fails.
3. Code you must read five files to understand.

Optimise against those three before anything else.

## Before you write a line

Writing code is the *last* step. Skipping the four below is what produces the
plausible-looking change that duplicates an existing helper, breaks a
convention, and fails review.

1. **Read the neighbours.** Open two or three files near where you are about to
   work. How do they name things? How do they report errors, log, test,
   structure a module? Your change should be indistinguishable in style from
   code that was already there. A technically better pattern applied
   inconsistently makes the codebase worse, not better — if you want to
   introduce one, say so explicitly and apply it to a whole seam, not one file.

2. **Search before you build.** Grep for the concept, not just the name:
   a date formatter might be `formatDate`, `toDisplayDate`, `humanize`, or live
   in `utils/time`. Duplicated logic is the single most expensive habit,
   because both copies get fixed at different times.

3. **Know what "done" means.** Restate the requirement as a testable sentence:
   "given X, the endpoint returns Y, and given malformed X it returns 400 with
   a message naming the bad field." If you cannot write that sentence, you do
   not yet know what to build — ask, or state the assumption you are proceeding
   under.

4. **Pick the smallest change that fully solves it.** Not the smallest
   *diff* — the smallest *concept*. Adding one parameter to an existing
   function beats adding a parallel function. But a hack that leaves the
   problem half-solved is not small, it is deferred.

## Where code belongs

Most bad code is well-written code in the wrong place. Before writing, decide
its home — `repo-architect` covers the repository-level version of this; the
per-change version is:

- **Put logic at the altitude that owns the decision.** Business rules do not
  belong in a controller, an HTTP handler, or a React component. Those are
  transport and presentation; they translate. If your handler contains an
  `if` about domain meaning ("gold customers skip the fee"), that `if` belongs
  in the domain layer where it can be tested without a request object.
- **Dependencies point one way.** Domain logic must not import transport,
  storage, or framework code. If it does, you can no longer test it, reuse it,
  or swap the database. Import cycles are a design error surfacing as a build
  error — fix the design.
- **Do not create a layer for one caller.** An interface with a single
  implementation and no second one planned is indirection with no payoff. Add
  it when the second implementation arrives; that is when you learn what the
  interface should actually be.
- **Keep related things together.** A feature's handler, logic, types, and
  tests living side by side beats those four files scattered across four
  top-level directories organised by kind.

## Naming

Naming is where the reader's understanding is built or destroyed, and it costs
nothing to get right at write time versus a rename across 40 files later.

**A name states what the thing is or does, in domain language.** Not its type,
not its implementation.

```ts
// Weak: type-shaped, tells the reader nothing they can't see.
const dataList = [];  const userObj = {};  function processData(d) {}

// Strong: says what it holds and what happens.
const pendingInvoices = [];  const signedInUser = {};
function chargeOverdueInvoices(invoices) {}
```

Concrete rules that resolve most naming arguments:

- **Length scales with scope.** `i` inside a three-line loop is fine. A module
  export called `mgr` is not. The further a name travels, the more it must
  carry on its own.
- **Booleans read as assertions**: `isExpired`, `hasPermission`, `shouldRetry`,
  `canPublish`. Then `if (isExpired)` reads as English.
- **Avoid negated names.** `notReady`/`disableCache` produce `if (!notReady)`,
  which readers misparse under stress. Name the positive: `isReady`,
  `cacheEnabled`.
- **Put units and currencies in the name**: `timeoutSeconds`, `sizeBytes`,
  `priceCents`, `distanceKm`. A shocking share of production bugs are a
  milliseconds value passed to a seconds parameter, and the type system will
  not catch it.
- **Functions are verb phrases; the verb tells you the cost and the effect.**
  `get*` is cheap and returns something. `fetch*`/`load*` does I/O and can
  fail. `compute*` is expensive but pure. `ensure*` is idempotent and may
  write. `validate*` throws or returns errors; `isValid*` returns a boolean.
  Do not name something `getUser` if it opens a socket — you have lied about
  the cost, and someone will call it in a loop.
- **Ban filler nouns as the whole name**: `data`, `info`, `item`, `object`,
  `value`, `temp`, `result`, `handler`, `manager`, `helper`, `util`,
  `processor`. They are placeholders that survived to production. `Manager` in
  particular almost always means "I did not decide what this is" — name it for
  its actual job (`SessionStore`, `RetryPolicy`, `PriceCalculator`).
- **Use the domain's word, exactly one word per concept.** If the business says
  "shipment", do not alternate between `delivery`, `parcel`, and `package`.
  A reader who greps `shipment` should find all of it.
- **Abbreviate only what the domain already abbreviates.** `url`, `id`, `http`,
  `db` are fine. `usr`, `calc`, `rsp`, `mgr`, `cfg` save four characters and
  cost a re-read every time.

Two tells that a name is wrong: you need a comment to explain the variable, or
you keep having to look up what it holds while writing the code below it.

## Function and method design

**One job, one altitude.** A function should either orchestrate (call a
sequence of named steps) or do detailed work — mixing the two is what produces
the 200-line function everyone is scared of. Named steps also mean the stack
trace tells you where you are.

```go
// Orchestration: reads like the description of the feature.
func PublishPost(ctx context.Context, id PostID) error {
    post, err := s.posts.Load(ctx, id)
    if err != nil { return fmt.Errorf("load post %s: %w", id, err) }
    if err := validateReadyToPublish(post); err != nil { return err }
    post.PublishedAt = s.clock.Now()
    if err := s.posts.Save(ctx, post); err != nil {
        return fmt.Errorf("save post %s: %w", id, err)
    }
    s.events.Emit(ctx, PostPublished{ID: id})
    return nil
}
```

- **Length is a symptom, not the rule.** There is no magic number, but past
  ~40 lines you are almost always mixing altitudes. Before extracting, check
  the extraction is *nameable*: if you cannot name the new function without
  "And" or "Helper", the seam is in the wrong place and you have made things
  worse.
- **Extract where a comment wanted to go.** `// now reconcile the balances`
  above a block is the block telling you it is a function called
  `reconcileBalances`.
- **Parameters: three is comfortable, five is a smell.** Long lists mean the
  function does too much, or the arguments are one concept that deserves a
  type. A `CreateOrderRequest` struct also makes call sites self-documenting
  and survives adding a field.
- **No boolean parameters.** `render(doc, true)` is unreadable at the call
  site, and the reader must open the definition to decode it. Split into
  `renderDraft`/`renderFinal`, or pass a named option/enum. This one rule
  removes a surprising amount of confusion.
- **Guard clauses over nested happy paths.** Handle the exceptional cases first
  and return; let the main logic sit unindented at the bottom. Nesting past
  three levels is a reliable sign that a guard clause or an extraction is
  missing.
- **Separate decisions from effects.** A function that computes *what should
  happen* and returns it, plus a thin caller that *does it*, is testable
  without mocks and reusable in a dry-run. Push I/O to the edges; keep the
  middle pure. This single habit is the biggest lever on testability.
- **Make illegal states unrepresentable.** A type with `status: "paid"` and an
  optional `paidAt` lets a paid order have no payment date. Model the states
  themselves (a tagged union / sealed class / enum with payloads) so the
  compiler rejects the impossible combination instead of you writing a runtime
  check you will forget somewhere.
- **Return early, return one shape.** Do not return a value on one path, `null`
  on another, and throw on a third; the caller cannot write correct handling
  for that. Pick a contract and hold it.

## Control flow

- **Handle errors and edge cases at the top; keep the main line at the
  bottom, unindented.** The reader should be able to skim the last third of a
  function and see the actual behaviour.
- **Prefer exhaustive dispatch to `if/else` chains** on a closed set — a
  `switch` on an enum, a match, or a lookup table. Where the language checks
  exhaustiveness, adding a case becomes a compile error at every site that
  needs updating instead of a silent fallthrough in production.
- **A lookup table beats a five-branch conditional** when the branches only
  select data. Conditionals should encode decisions, not act as a map.
- **Loops: name what you are accumulating.** If a loop body exceeds a screen,
  extract it. If it is filtering-then-transforming, use the language's
  filter/map so the intent is on the first line instead of implied by control
  flow.
- **Never leave an empty catch or an ignored return.** If ignoring is truly
  correct, say why in one line — an unexplained swallow is indistinguishable
  from a bug, and it is the single hardest defect class to find later.

## Errors

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

## Comments and documentation

Code says *what*. Comments exist for what code cannot say.

Write comments for: **why** a non-obvious choice was made, invariants a caller
must maintain, links to the issue/spec/RFC that explains a workaround, units
and ranges that are not in a type, and warnings about a subtle interaction.

```ts
// Stripe rejects amounts over 999999 cents per charge, so large invoices are
// split. Splitting is safe because the payment intent is idempotent per
// invoice line. See INC-4471.
```

Delete comments that restate the code (`// increment i`), commented-out code
(git remembers it), and changelog comments in source (`// modified by ...`).
A comment that explains *what a line does* is a renaming opportunity in
disguise — fix the name and delete the comment.

Public API surface gets a doc comment saying what it does, what it returns,
what it throws, and any non-obvious constraint. `docs-craft` covers the
per-language formats and the repository-level documentation set.

`TODO`s need an owner and a condition: `// TODO(akhil): remove once the v2
migration lands — tracked in #412`. A bare `// TODO: fix` is decoration.

## State, mutation, and dependencies

- **Narrow every scope you can.** Declare variables where first used, at the
  innermost level that works, `const`/`final` by default. A variable that is
  assigned once and never reassigned is one less thing to track while reading.
- **No global mutable state.** It makes behaviour depend on execution order,
  breaks tests in ways that only appear when they run in a different order, and
  makes concurrency unsafe. Pass dependencies in explicitly — that is also what
  makes them substitutable in tests.
- **Single source of truth.** The same fact stored in two places will diverge.
  Derive one from the other, or store it once.
- **Inject what you cannot control**: clock, randomness, filesystem, network,
  environment. `Date.now()` buried in a function makes the behaviour untestable
  and time-dependent; a `clock` dependency makes it a one-line test.
- **Adding a dependency is a permanent commitment.** Before adding one: is it
  maintained, what does it pull in transitively, what is the license, and could
  20 lines of your own do it? For anything you do add that touches your domain,
  wrap it behind a small interface you own, so replacing it later is a
  contained change rather than an archaeology project.

## Concurrency

Only reach for it when there is a measured reason. Concurrency bugs are
non-deterministic, survive code review, and reproduce only under load.

- Prefer message passing / queues over shared mutable memory.
- Every blocking call gets a **timeout**; every long operation gets a
  **cancellation path** (context, signal, token). Unbounded waits are how
  systems hang instead of failing.
- **Bound your parallelism.** Unlimited goroutines/tasks/promises against a
  database is a self-inflicted denial of service. Use a pool or a semaphore.
- Anything that can be retried must be **idempotent**, and anything over a
  network will be retried.
- Document the concurrency contract of shared types: which methods are safe to
  call from multiple threads, and what lock protects what.

## When to restructure instead of patch

Adding another special case to code that is already the wrong shape is how
files become untouchable. Stop and restructure when you hit these:

- The third special case lands in the same conditional.
- You cannot write a test for your change without instantiating half the system.
- You must change the same logic in more than one place for one behaviour change.
- You cannot name the function honestly any more because it does three things.
- Every change to this file causes an unrelated regression.

Restructure **safely**, in this order, so that a rewrite is a series of boring
steps rather than a risky rewrite:

1. Get a test around the current behaviour first — characterisation tests, even
   ugly ones. Without them you are not refactoring, you are rewriting and
   hoping.
2. Make the structural change **without changing behaviour**, in its own commit
   with no logic edits mixed in. A reviewer must be able to see that a move is
   only a move.
3. Run the tests. They should pass unchanged — that is the proof.
4. Then make the behaviour change, in a separate commit.

Say so plainly when you do this: "the pricing logic had three call sites doing
the same rounding differently, so I extracted `roundToCents` first, then added
the new tier." Silent large refactors inside a feature PR are unreviewable and
get rejected on principle.

Do not restructure code you are not otherwise touching just because you would
have written it differently. Scope discipline is part of craft.

## Before you call it done

Read your own diff as if someone else wrote it and you are looking for the bug.
Specifically check:

- Does every new name still look right now that the code is written?
- What happens on the empty input, the missing key, the zero, the huge value,
  the concurrent second call?
- Is every error path either handled or deliberately propagated with context?
- Does anything log or return a secret, token, password, or personal data?
- Is there a resource — file, socket, transaction, lock — that leaks on the
  error path?
- Did you leave debugging output, commented code, or an unexplained magic
  number?
- Would a stranger know why this code exists, from the code and its comments?

`ship-quality` carries the full pre-commit gate (running the repo's own lint,
type, and test commands, commit messages, and the honest report of what you
did and did not do). `testing-craft` covers writing the tests themselves.

## References

Read the file that matches what you are working on; do not read them all.

- `references/languages.md` — idioms, footguns, and the specific rules that
  matter per language: TypeScript/JavaScript, Go, Rust, Java/Kotlin, C#,
  Ruby, shell, and SQL. Read the section for the language you are writing.
- `references/errors-and-boundaries.md` — worked patterns for error taxonomies,
  validation at boundaries, retries, timeouts, and idempotency.
- `references/anti-patterns.md` — a before/after catalogue of the specific
  constructs that most often make code unreadable, with the fix for each.
  Read this when a reviewer says "this is hard to follow" and you are not sure
  why.
