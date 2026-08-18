---
name: testing-craft
description: Write tests that catch bugs and survive refactoring — what to test and what to skip, Arrange-Act-Assert, naming, determinism, disciplined mocking, the edge cases people forget, and coverage as a diagnostic not a target. Use whenever tests are written, fixed, or reviewed: "write tests for this", "add test coverage", "the tests are flaky", "this test is failing", "write a regression test", or when finishing a feature that ships without tests. Covers pytest, vitest/jest, go test, cargo test, and JUnit.
---

# Testing craft

Most suites fail one of two ways: so thin a real bug ships, or so brittle that
every refactor breaks fifty tests asserting implementation details. Both come
from not being clear what a test is *for*.

**A test earns its place by failing when the behaviour breaks, and only then.**
Apply that to each test you write:

- Would it fail if the feature broke? If not, it is decoration.
- Would it fail if someone renamed a private method without changing behaviour?
  If so, it is a liability — it gets deleted during the first refactor, taking
  its coverage with it.

Tests are also the fastest documentation in the repository: a reader who wants
to know what a function does opens its tests first, because they show real
inputs and real expected outputs.

## The standing rules

1. **Test observable behaviour at the public boundary**, not internals. Assert
   the outcome (`response.status == 200`), not the mechanism
   (`repo.save.call_count == 1`) — the latter breaks the moment someone adds a
   legitimate retry.
2. **Arrange, Act, Assert — with exactly one act.** Two acts and a failure in
   the first hides everything after it, and the name cannot describe both.
3. **Arrange only what the test needs.** A twelve-field fixture where two matter
   buries the point. Use a factory with defaults and override the one relevant
   field, so the setup states what the test is about.
4. **No logic in tests** — no loops, conditionals, or computed expectations. A
   test containing `expected = price * 1.2` reimplements the code under test and
   passes when both are wrong. Write the literal; use parametrisation for many
   cases so each stays a separately named result.
5. **Name for the failure report**: `<unit>_<condition>_<expected>`, e.g.
   `test_transfer_with_insufficient_funds_raises`. It is read out of context by
   someone who did not write it. A name that is hard to write means the test is
   doing too much.
6. **Determinism is not optional.** No real clock, real randomness, real network,
   shared mutable state, or `sleep`. Inject the clock, seed the generator, fake
   the boundary, poll for the condition. Every test must pass alone and in any
   order.
7. **Every bug fix gets a regression test written first**, watched failing for
   the right reason, then fixed. It is the only test you know has caught a real
   defect.
8. **Prefer a fake to a mock.** A ten-line in-memory repository that really
   stores and retrieves beats five stubbed calls: it exercises real behaviour and
   is reusable. If a unit needs many mocks to be testable, fix the design.
9. **Never skip, weaken, or delete a failing test to reach green** without saying
   so explicitly. A flaky test is worse than no test — it trains everyone to
   re-run CI instead of reading failures. Fix the cause or remove it and say so.

## Before you call it done

Every new behaviour has a test; the suite passes from a clean checkout and in a
random order; no test depends on the machine, clock, network, or another test;
and you have said which risks you chose not to cover.

## Read the reference that matches your task

| If you are… | Read |
|---|---|
| Deciding what is worth testing, reaching for a mocking library, hunting edge cases, or facing a failing test | `references/what-to-test.md` |
| Writing tests in a specific framework | `references/frameworks/` — `pytest`, `vitest-jest`, `go`, `rust`, `junit` |
| Considering property-based, snapshot, or contract tests; testing async or concurrent code; using real databases; or characterising legacy code | `references/advanced.md` |
