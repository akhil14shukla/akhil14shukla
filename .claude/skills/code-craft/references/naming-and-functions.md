# Naming, function design, and control flow

The three decisions that determine whether a stranger can read your code. Read
this when writing new functions, when a reviewer says something is hard to
follow, or when you are unsure what to call something.

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
