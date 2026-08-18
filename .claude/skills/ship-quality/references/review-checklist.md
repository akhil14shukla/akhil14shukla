# Deep review checklist

Read this for the deep review pass on a high-stakes change — anything touching
money, authentication, personal data, a public API, a migration, or a hot path.

The gate in `SKILL.md` covers every change. This is the longer pass for changes
where the stakes justify it: anything touching money, authentication, personal
data, a public API, a migration, or a hot path.

Work top-down. Design problems make the rest irrelevant, so they come first.

## Read your own diff as a stranger

Look at the actual diff, not your memory of what you wrote. `git diff` and
`git diff --staged`, file by file. You are looking for the things that are
invisible while writing and obvious while reading.

```bash
git diff                      # unstaged
git diff --staged             # staged
git status                    # anything accidentally added, anything forgotten
git diff --stat               # is the change the size you think it is?
```

Ask, in this order — design first, because a design problem is not fixable by
polishing:

- **Does this change belong here?** Right layer, right module, consistent with
  how the codebase already does this?
- **Does it do what was asked, all of it?** Re-read the original request. It is
  common to solve 80% and to have stopped noticing the other 20%.
- **Is there anything in the diff I did not mean to include?** Debug prints,
  commented-out code, a stray file, a formatting change to an unrelated file, a
  version bump you did not intend, a `.env`.
- **What happens on the unhappy path?** Empty input, missing key, zero, a
  negative number, a value ten times bigger than expected, the dependency being
  down, the same request arriving twice.
- **Does every error path either handle the failure or propagate it with
  context?** No silent `catch {}`, no ignored return value without a stated
  reason.
- **Does anything leak on the error path** — a file handle, a connection, a
  transaction, a lock?
- **Would a stranger understand why this code exists** from the names and the
  comments?

Fix what you find *before* running the tests, not after — the tests will not
tell you about any of it.

---

## Design

- Does this change belong in this module, at this layer? Would a newcomer look
  for it here?
- Is it consistent with how the codebase already solves this problem, or does it
  introduce a second way of doing the same thing?
- Is it solving the problem that exists, or a speculative future one? An
  interface with one implementation, a config flag nobody sets, and a plugin
  system with one plugin are all costs paid now for a benefit that may never
  arrive.
- Could this be meaningfully simpler? Is there an existing helper it should use?
- Does it introduce a dependency in the wrong direction — domain code importing
  a framework, a shared module importing a feature?

## Correctness

- Walk the happy path once, reading as if you had not written it.
- Then walk each error path. What does the caller see? Is any state left
  half-updated?
- Boundaries: zero, one, empty, null, negative, maximum, one past the limit,
  first and last element.
- Off-by-one in every index, slice, range, and loop bound.
- Are comparisons using the right operator (`<` vs `<=`) and the right type
  (string vs number)?
- Floating point: any money or exact-equality comparison?
- Time: timezone handling, DST, month ends, a duration assumed positive.
- Are all the cases of an enum or union handled, and will adding a new case
  cause a compile error rather than a silent fallthrough?

## Data and persistence

- Is the migration reversible, and has it been run against production-sized
  data? Adding a column, an index, or a constraint can lock a large table.
- Is the change backward compatible with the currently-deployed code? During a
  rolling deploy, both versions run at once — a migration that removes a column
  the old code still reads breaks it.
- Are new columns nullable or defaulted, so existing rows remain valid?
- Are constraints enforced in the schema (`NOT NULL`, foreign keys, unique)
  rather than only in application code?
- Is anything read-modify-written without a lock, a transaction, or an atomic
  operation? That is a lost update under concurrency.
- Is the transaction scope right — not too wide (holding locks across a network
  call), not too narrow (a multi-step operation that can half-apply)?

## API compatibility

- Does this change break an existing caller? Removing a field, renaming one,
  narrowing an accepted type, adding a required parameter, or changing an error
  code all do.
- Are new fields optional, with a sensible default?
- Is the change versioned or feature-flagged if it must break?
- Are error responses documented and stable? Callers branch on them.
- Is there a deprecation path with a timeline, rather than a removal?

## Concurrency

- What happens if this runs twice simultaneously? Is the operation idempotent?
- Is shared mutable state protected, and is the lock scope minimal?
- Can two locks be acquired in different orders anywhere? That is a deadlock.
- Is every blocking call bounded by a timeout, and every long operation
  cancellable?
- Is parallelism bounded, sized to what the downstream can actually serve?
- Is there a race between check and use (`if exists: read`) that should be one
  atomic operation?

## Security

- Every external input validated at the boundary, with a size limit.
- Parameterised queries; no shell or `eval` built from input.
- Authorisation checked on the *object*, not just the session — "is this order
  the requesting user's order", not merely "is someone logged in". This is the
  most common real vulnerability in application code.
- No secrets in code, logs, error messages, or tests. Nothing sensitive returned
  to a caller who should not see it.
- Output encoded for its destination (HTML escaping, header sanitisation).
- New dependency: maintained, widely used, appropriately licensed, pinned.
- Cryptography from a library, never hand-rolled; a CSPRNG for anything
  security-relevant.

## Operations

- Will you be able to debug this at 3am from the logs alone? Are the log
  messages at the right level, with enough context (ids, operation) and no
  sensitive data?
- Are there metrics for the things that matter — rate, errors, duration?
- What happens when the dependency this calls is down or slow? Timeout, retry,
  circuit break, or fail fast — and is that the right choice for this operation?
- Is the failure mode safe? Fail closed for anything security- or money-related,
  fail open only for genuinely optional enrichment.
- Is there a rollback path? A change that cannot be rolled back (a destructive
  migration, a one-way data transform) needs to be called out explicitly.
- Does anything new need a runbook entry or an alert?

## Tests

- Does a test exist that fails if this behaviour breaks? Verify by breaking it
  deliberately and watching the test go red — this is the only way to be sure.
- Do the tests assert behaviour rather than implementation details?
- Are the error paths tested, not just the happy path?
- Is anything non-deterministic — real time, real randomness, real network,
  shared state, sleeps?
- For a bug fix: does the regression test fail without the fix?

## Readability

- Would someone unfamiliar with this code understand it without asking?
- Does every name still look right now the code is written?
- Is there a comment explaining *why* anywhere it is non-obvious — and no
  comment merely restating *what*?
- Is any function doing more than one job, or sitting at two altitudes at once?
- Is there leftover debugging output, commented-out code, or an unexplained
  magic number?
