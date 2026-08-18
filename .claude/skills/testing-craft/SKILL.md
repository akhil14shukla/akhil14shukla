---
name: testing-craft
description: Write tests that actually catch bugs and survive refactoring — what to test and what to skip, Arrange-Act-Assert structure, naming, determinism, the edge cases people forget, disciplined mocking, and using coverage as a diagnostic rather than a target. Use this whenever tests are being written, fixed, or reviewed: "write tests for this", "add test coverage", "the tests are flaky", "this test is failing", "write a regression test", "how do I test this", or when finishing any feature that ships without tests. Covers pytest, vitest/jest, go test, cargo test, and JUnit.
---

# Testing craft

Most test suites fail one of two ways: they are so thin that a real bug ships,
or so brittle that every refactor breaks fifty tests that were asserting
implementation details. Both come from the same root cause — not being clear
about what a test is *for*.

**A test earns its place by failing when the behaviour breaks, and only then.**
Apply that sentence to each test you write:

- Would this test fail if the feature broke? If no, it is decoration.
- Would this test fail if someone renamed a private method without changing
  behaviour? If yes, it is a liability — it will be deleted during the first
  refactor, along with the coverage it provided.

Tests are also the fastest documentation in the repository. A reader who wants
to know what a function does opens its tests before its implementation, because
tests show real inputs and real expected outputs.

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

## Structure: Arrange, Act, Assert

```py
def test_expired_token_is_rejected():
    # Arrange — everything the behaviour needs, and nothing else
    token = Token(expires_at=datetime(2024, 1, 1, tzinfo=UTC))
    clock = FrozenClock(at=datetime(2024, 6, 1, tzinfo=UTC))

    # Act — exactly one call: the behaviour under test
    result = validate(token, clock)

    # Assert — the outcome the caller cares about
    assert result.ok is False
    assert result.reason == "expired"
```

- **One behaviour per test.** Not one assertion — several assertions about the
  same outcome are fine — but one *act*. When a test has two acts, a failure in
  the first hides everything after it, and the name cannot describe both.
- **Arrange only what the test needs.** A twelve-field fixture where two fields
  matter buries the point. Use a factory with defaults and override only the
  relevant field: `make_order(status="paid")` says exactly what this test is
  about.
- **Assert the outcome, not the mechanism.** `assert response.status == 200 and
  response.json()["id"] == order.id` is a contract. `assert
  repo.save.call_count == 1` is an implementation detail that will break the
  moment someone adds a legitimate retry.
- **No logic in tests** — no loops, conditionals, or computed expectations. A
  test containing `expected = price * 1.2` reimplements the code under test, so
  it passes when both are wrong. Write the literal: `assert total == 1200`.
  Where you genuinely need many cases, use the framework's parametrisation,
  which keeps each case a separate named result.

## Naming

A test name is read in a failure report, out of context, by someone who did not
write it. It should say what broke without them opening the file.

Use `<unit>_<condition>_<expected outcome>`:

```
test_transfer_with_insufficient_funds_raises_insufficient_funds
test_parse_date_accepts_iso_8601_with_offset
test_cart_total_applies_bulk_discount_above_ten_items
```

Not `test_transfer_2`, `test_edge_case`, `test_it_works`. If a name is hard to
write, the test is usually doing too much — that difficulty is information.

## Determinism

A flaky test is worse than no test: it trains everyone to re-run CI instead of
reading failures, and eventually a real failure gets re-run away. The causes are
few and all preventable:

- **Real time.** `datetime.now()`, `Date.now()`, `time.Now()` make behaviour
  depend on when the suite runs — and produce a test that fails at a month
  boundary or in another timezone. Inject a clock, or freeze time
  (`freezegun`, `vi.useFakeTimers`, a `Clock` interface).
- **Real randomness.** Seed it, or inject the generator.
- **Real network.** Never in a unit test. Use a fake at your own boundary, or a
  local stub server for integration tests. Tests that hit a live API fail when
  someone else's service has a bad day.
- **Shared mutable state between tests** — module globals, a session-scoped
  fixture that tests mutate, a database row left behind. Each test must set up
  and tear down its own state, and must pass when run alone and in any order.
  Run the suite in random order periodically to prove it.
- **Sleeps.** `sleep(2)` is both slow and unreliable. Wait for the condition
  (poll with a timeout), or make the async boundary injectable.
- **Filesystem paths and the working directory.** Use the framework's temp
  directory fixture; never write beside the source.

When a test does flake, fix the cause or delete the test. Adding a retry to a
flaky test is how a suite becomes decorative.

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

## Before you call it done

- Every new behaviour has a test; every fixed bug has a regression test.
- The suite passes from a clean checkout, and passes in a different random
  order.
- No test depends on the machine, the clock, the network, or another test.
- Test names describe behaviour; failures are readable without opening the file.
- You have said out loud which risks are not covered and why.

## References

- `references/frameworks.md` — the idioms that matter per framework: pytest
  (fixtures, parametrize, tmp_path, monkeypatch), vitest/jest, go test
  (table-driven, subtests, `t.Cleanup`), cargo test, and JUnit 5 + AssertJ.
  Read the section for the stack you are in.
- `references/advanced.md` — property-based testing, golden/snapshot tests,
  contract tests, testing async and concurrent code, integration tests with real
  databases via containers, and how to characterise legacy code before changing
  it.
