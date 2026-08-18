# Placement, state, and knowing when to restructure

Where code belongs, how to keep state manageable, and the safe procedure for
restructuring rather than patching. Read this when deciding where a change goes,
when adding a dependency or shared state, or when a file has become hard to
change safely.

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
