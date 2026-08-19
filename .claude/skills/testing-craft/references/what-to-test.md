# What to test, what to mock, and what coverage means

Read this when deciding which tests are worth writing, when a suite feels
brittle or thin, when reaching for a mocking library, or when a test fails and
you are tempted to change it.

## What to test, and what to skip

**Test the observable behaviour of a unit at its public boundary.** For a
module, that is its exported functions. For a service, its HTTP contract. For a
class, its public methods.

Worth testing, roughly in order of payoff:

1. **The business rules** — pricing, permissions, state transitions, validation.
   These encode decisions someone will get wrong, and they are cheap to test
   when the logic is pure (which is one more reason to keep I/O at the edges).
2. **Every bug you fix.** Write the failing test *first*, watch it fail for the
   right reason, then fix. A bug that happened once will happen again, and this
   is the only test you know for certain has caught a real defect.
3. **Edge and error paths.** They are where the bugs are, and they are the least
   likely to be exercised by manual testing.
4. **Contracts across boundaries** — the shape of what you return to callers,
   what you accept, what you persist.

Not worth testing: language features, third-party library internals, trivial
getters and setters, and generated code. A test asserting that `dataclass`
assigns fields tests Python, not you.

**The mix**: many fast tests with no I/O, fewer tests that touch a real database
or a real HTTP boundary, very few end-to-end tests. Not because integration
tests are bad — they catch what unit tests cannot — but because they are slow and
tell you *that* something broke rather than *what*. If a suite takes more than a
couple of minutes, people stop running it, and an unrun test is worth nothing.

## Mocking, with discipline

Over-mocking is the most common way a suite becomes brittle. A test built from
six mocks asserts that your code calls the functions you told it to call — which
is true by construction, and stays true when the code is wrong.

Rules that keep this under control:

- **Mock at the boundary you own**, not deep inside. Substitute the whole
  `PaymentGateway` interface; do not patch a method three layers into someone
  else's library, which breaks silently when they refactor.
- **Do not mock what you do not own.** Wrap the third-party client in your own
  thin interface, then fake that. You get a stable seam *and* a place to test
  the real integration once.
- **Prefer a fake to a mock.** A ten-line `InMemoryUserRepository` that really
  stores and retrieves is more useful than a mock with five `when(...)` stubs:
  it exercises real behaviour, reads clearly, and is reusable across the suite.
- **Do not assert on call counts and argument order** unless the interaction
  *is* the behaviour (an email must be sent exactly once; a payment must not be
  charged twice). Otherwise assert on the resulting state.
- If a unit needs many mocks to be testable, that is a design signal: it has too
  many dependencies, or logic and I/O are tangled. Fixing the design is usually
  faster than fighting the test.

## The edge cases people forget

Walk this list for anything non-trivial — it is where most escaped bugs live:

- **Empty**: empty string, empty list, empty file, no rows, no results.
- **One**: the single-element case, where off-by-one and pluralisation break.
- **Many**: enough to trip pagination, batching, or an O(n²) path.
- **Boundaries**: zero, negative, exactly the limit, one over, max int, the
  first and last item.
- **Absent**: null/None/undefined, a missing key, an optional field not sent.
- **Malformed**: wrong type, unparseable date, invalid enum value, truncated
  JSON.
- **Text**: unicode, emoji, right-to-left, a name with an apostrophe, leading
  and trailing whitespace, a string that looks like a number.
- **Time**: timezones, DST transitions, leap years, month ends, a timestamp in
  the past when the future was assumed.
- **Money**: rounding, fractional cents, negative amounts, currency mismatch.
- **Failure of a dependency**: timeout, 500, connection refused, partial
  response, a retry that duplicates.
- **Concurrency**: the same operation twice at once, ordering assumptions.
- **Authorisation**: the wrong user, no user, a user whose permission changed
  mid-request.

You will not test all of these for every function. Read the list, pick the ones
that are plausible for this code, and say which risks you chose not to cover.

## Coverage

Coverage tells you what is definitely *not* tested. It cannot tell you what is
well tested — a test with no assertions gives full coverage of the lines it
runs.

Use it as a diagnostic: look at the uncovered lines and ask whether each one
matters. Error branches showing red is a real finding. Chasing a percentage
target produces tests written to touch lines, which is how suites fill with
assertions nobody believes. If a number is mandated, apply it to *new* code
(patch coverage) rather than the whole repository, and treat error paths and
business rules as the parts that must be covered.

## When a test fails

Read the failure before changing anything. A failing test is information, and
the instinct to make it green is how bugs get shipped.

1. **Is the test right and the code wrong?** Fix the code.
2. **Did the requirement change?** Update the test *deliberately*, and say so in
   the commit message — this is the one legitimate reason to change a test's
   expectations.
3. **Is the test asserting an implementation detail you just changed?** Rewrite
   it to assert behaviour instead. This is the moment to fix the brittleness,
   not paper over it.

Never delete or `skip` a failing test to get to green without saying so
explicitly to the user. A skipped test is a silent hole, and it is the one thing
in a suite that actively misleads.
