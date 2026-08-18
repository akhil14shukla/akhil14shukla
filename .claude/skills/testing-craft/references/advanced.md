# Advanced testing techniques

Read this when a plain example-based test is a poor fit — property-based,
snapshot, or contract tests; async and concurrent code; real databases; or
characterising legacy code before changing it.

Reach for these when the plain example-based test is a poor fit. Each has a
narrow sweet spot; using them everywhere makes a suite slower and harder to read.

## Property-based testing

Instead of asserting one input/output pair, assert a *property* that must hold
for all inputs, and let the framework generate hundreds of cases and shrink any
failure to the minimal reproducer.

```py
from hypothesis import given, strategies as st

@given(st.lists(st.integers()))
def test_sort_is_idempotent_and_preserves_length(xs: list[int]) -> None:
    once = sorted(xs)
    assert sorted(once) == once
    assert len(once) == len(xs)
```

Good properties: round-trips (`decode(encode(x)) == x`), invariants (a balance
never goes negative), idempotence, commutativity, and agreement with a slow but
obviously-correct reference implementation.

Best value on: parsers and serialisers, encoders, arithmetic, data structures,
and anything where you feel you cannot think of all the cases — which is exactly
where hand-written examples miss. Tools: `hypothesis` (Python), `fast-check`
(TS), `proptest`/`quickcheck` (Rust), `gopter` (Go), `jqwik` (Java).

Keep the hand-written examples for the interesting specific cases; property
tests complement them rather than replacing them.

## Golden / snapshot tests

Capture a known-good output and assert future runs match. Useful for large
structured outputs — rendered HTML, generated code, CLI help text, complex JSON.

```bash
go test ./... -update       # regenerate goldens deliberately
```

The failure mode is snapshot rot: someone regenerates on every failure, and the
snapshot stops meaning anything. Rules that prevent it:

- **Review the diff like code.** A changed snapshot is a changed behaviour.
- Keep snapshots small and focused; a 2,000-line snapshot cannot be reviewed, so
  it will not be.
- Never auto-update in CI.
- Scrub non-deterministic fields (timestamps, ids, durations) before comparing,
  or the snapshot fails for no reason and gets regenerated blindly.

## Contract tests

When two services talk, each side's tests can pass while the integration is
broken. A contract test pins the shared shape: the consumer declares what it
needs, the provider verifies it can supply it (Pact and similar), or both sides
validate against one committed schema (OpenAPI, protobuf, JSON Schema).

The cheap version that catches most of the value: commit the schema, and have
both sides' test suites validate real requests and responses against it.

## Testing async and concurrent code

- **Never `sleep` to wait.** Poll for the condition with a timeout, or expose a
  completion signal. A sleep is both slow and a race that fails under CI load.
- Use the framework's fake timers for debounce, retry, and backoff logic —
  otherwise a retry test takes as long as the real backoff.
- Test concurrency properties directly: run the operation twice simultaneously
  and assert the invariant (exactly one charge, no lost update).
- Run with the race detector where one exists (`go test -race`, TSan). Race bugs
  do not reproduce on demand; the detector is the only reliable way to see them.
- Give every async test a timeout so a hang fails the suite instead of stalling
  CI.

## Integration tests with real infrastructure

An in-memory substitute for a database tests a different SQL dialect than the
one you ship on. Use a real one in a container:

```py
@pytest.fixture(scope="session")
def postgres():
    with PostgresContainer("postgres:16") as pg:
        yield pg.get_connection_url()
```

- Start the container once per session; give each test its own transaction and
  roll it back, or its own schema. That keeps tests isolated without paying
  startup cost per test.
- Mark them (`@pytest.mark.integration`, a build tag, a separate task) so the
  fast suite stays fast and can run without Docker.
- Do not mock what you are integrating with — the entire point is fidelity.

## Characterising legacy code

To change code that has no tests, first capture what it currently does. These
tests do not assert what the code *should* do; they pin what it *does*, so a
refactor that changes behaviour shows up immediately.

1. Find the seam — the function or endpoint you can call.
2. Feed it realistic inputs and record the outputs, including the odd ones.
3. Assert on those recordings, with a comment saying they are characterisation,
   not specification.
4. Refactor. The tests must stay green.
5. Afterwards, replace them with real specification tests as you learn what the
   behaviour *should* be, and delete any that pinned a bug.

This is the safety net referenced by `repo-architect` before a restructure and
by `code-craft` before a rewrite.

## Mutation testing

Coverage says a line ran; mutation testing asks whether any test would notice if
that line were wrong. It mutates the code (flipping `<` to `<=`, removing a
call) and reports mutants your suite failed to kill — those are the assertions
you are missing.

Expensive to run, so use it occasionally on the most critical module rather than
in every CI run. Tools: `mutmut`/`cosmic-ray` (Python), `stryker` (JS/TS),
`pitest` (Java), `cargo-mutants` (Rust).

## Performance regression tests

Assert a *bound*, never an absolute time — CI machines vary, and a test that
asserts "under 100ms" will flake forever.

- Assert complexity behaviour: doubling the input must not quadruple the work.
- Assert operation counts: "renders 1,000 rows in ≤ 3 queries" catches an N+1
  reliably and deterministically, unlike a timing assertion.
- For real timing, use a benchmark harness with a tracked baseline
  (`pytest-benchmark`, `criterion`, `go test -bench`) and alert on a percentage
  regression, outside the correctness suite.
