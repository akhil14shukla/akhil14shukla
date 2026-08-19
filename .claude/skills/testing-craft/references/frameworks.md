# Test framework idioms

Read the section for your stack. Each covers the features that change how tests
read, plus the specific traps in that framework.

## Contents

- [pytest (Python)](#pytest-python)
- [vitest / jest (TypeScript)](#vitest--jest-typescript)
- [go test](#go-test)
- [cargo test (Rust)](#cargo-test-rust)
- [JUnit 5 (Java/Kotlin)](#junit-5-javakotlin)

## pytest (Python)

**Parametrize instead of looping.** Each case becomes a separately named result,
so a failure tells you which input broke.

```py
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2024-01-15", date(2024, 1, 15)),
        ("2024-01-15T10:30:00Z", date(2024, 1, 15)),
        pytest.param("15/01/2024", None, id="rejects-day-first-format"),
    ],
)
def test_parse_date(raw: str, expected: date | None) -> None:
    assert parse_date(raw) == expected
```

**Fixtures for setup, with the narrowest scope that works.**

```py
@pytest.fixture
def order() -> Order:                    # function scope: fresh per test
    return Order(id=OrderId(1), lines=(OrderLine(sku="A", qty=2),))

@pytest.fixture(scope="session")
def db_engine():                         # expensive, shared — must stay read-only
    engine = create_engine(TEST_URL)
    yield engine
    engine.dispose()
```

A session-scoped fixture that tests *mutate* creates order dependence — the
classic "passes alone, fails in CI" bug. Share connections; do not share data.

**Built-in fixtures worth knowing**: `tmp_path` (real filesystem, auto-cleaned),
`monkeypatch` (env vars, attributes, cwd — reverted automatically), `capsys`
(stdout/stderr), `caplog` (log records, so you can assert on a warning without
parsing text).

**Assert failures, precisely:**

```py
with pytest.raises(InsufficientFunds, match="balance 50 < 100"):
    account.withdraw(100)
```

Without `match`, the test passes on *any* `InsufficientFunds`, including one
raised for the wrong reason.

**Traps**: a mutable default in a fixture return value shared across tests;
`assert` on floats without `pytest.approx`; `monkeypatch.setattr` targeting the
definition module rather than where the name was imported (patch where it is
*used*: `myapp.service.requests`, not `requests`); and `-p no:randomly` hiding
order dependence — run with `pytest-randomly` occasionally to expose it.

Useful invocations: `pytest -x` (stop at first failure), `--lf` (last failed),
`-k "expr"` (select by name), `--durations=10` (find the slow ones).

---

## vitest / jest (TypeScript)

```ts
describe('cartTotal', () => {
  it('applies the bulk discount above ten items', () => {
    const cart = makeCart({ items: 11 });
    expect(cartTotal(cart)).toBe(990);
  });

  it.each([
    [0, 0],
    [1, 100],
    [10, 1000],
  ])('charges full price for %i items', (items, expected) => {
    expect(cartTotal(makeCart({ items }))).toBe(expected);
  });
});
```

- `toBe` for primitives and identity, `toEqual` for deep structural equality,
  `toStrictEqual` when `undefined` keys and class identity matter.
- Async: `await expect(fn()).rejects.toThrow(HttpError)` — a forgotten `await`
  makes the assertion silently pass.
- Fake timers (`vi.useFakeTimers()` / `jest.useFakeTimers()`) with
  `advanceTimersByTime` for debounce, retry, and polling logic; always restore
  in `afterEach`.
- `vi.mock('./module')` is hoisted above imports — a common surprise. Prefer
  dependency injection over module mocking where you control the code.
- React: use Testing Library and query the way a user does (`getByRole`,
  `getByLabelText`), not by test id or class name. `userEvent` over `fireEvent`
  so the interaction is realistic.
- Reset state between tests: `restoreMocks: true` and `clearMocks: true` in the
  config, so a stub does not leak into the next file.

---

## go test

**Table-driven with subtests** is the idiomatic default: each case is named,
runnable in isolation (`go test -run 'TestParse/rejects_empty'`), and failures
say which row broke.

```go
func TestParseDuration(t *testing.T) {
	tests := []struct {
		name    string
		in      string
		want    time.Duration
		wantErr bool
	}{
		{name: "seconds", in: "30s", want: 30 * time.Second},
		{name: "rejects empty", in: "", wantErr: true},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := ParseDuration(tt.in)
			if (err != nil) != tt.wantErr {
				t.Fatalf("ParseDuration(%q) error = %v, wantErr %v", tt.in, err, tt.wantErr)
			}
			if got != tt.want {
				t.Errorf("ParseDuration(%q) = %v, want %v", tt.in, got, tt.want)
			}
		})
	}
}
```

- `t.Fatalf` stops this test (use when continuing would panic); `t.Errorf`
  records and continues (use for independent assertions).
- Failure messages state *what was called, what came back, what was expected* —
  `got = X, want Y`. That convention makes any Go failure readable.
- `t.Cleanup(fn)` over `defer` for teardown: it runs after subtests too.
- `t.Parallel()` inside subtests to speed the suite — only if the cases share no
  state.
- `t.TempDir()` for filesystem work. `httptest.NewServer` for HTTP boundaries.
- **Always run `go test -race` in CI.** It finds data races that are otherwise
  invisible until production load.
- Golden files (`-update` flag convention) for large expected outputs.

---

## cargo test (Rust)

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_iso_dates() {
        assert_eq!(parse("2024-01-15").unwrap(), Date::new(2024, 1, 15));
    }

    #[test]
    fn rejects_day_first_format() {
        assert!(matches!(parse("15/01/2024"), Err(ParseError::Format(_))));
    }

    #[test]
    #[should_panic(expected = "capacity must be > 0")]
    fn rejects_zero_capacity() {
        Buffer::new(0);
    }
}
```

- Unit tests live in-file under `#[cfg(test)]` so they can reach private items;
  `tests/` exercises only the public API, which is the real contract check.
- `assert_eq!` prints both values on failure; a bare `assert!(a == b)` does not —
  prefer the former.
- `matches!` for asserting an error *variant* without requiring `PartialEq`.
- Doc tests run with `cargo test`, so examples in `///` comments cannot rot.
- `#[should_panic(expected = "...")]` — always include `expected`, or the test
  passes on any panic, including a typo.
- `proptest` or `quickcheck` for property tests; `insta` for snapshots.

---

## JUnit 5 (Java/Kotlin)

```java
@Test
@DisplayName("transfer with insufficient funds leaves both balances unchanged")
void transferWithInsufficientFunds() {
    var from = new Account("A", Money.of(50));
    var to   = new Account("B", Money.of(0));

    assertThatThrownBy(() -> service.transfer(from, to, Money.of(100)))
        .isInstanceOf(InsufficientFundsException.class)
        .hasMessageContaining("balance 50");

    assertThat(from.balance()).isEqualTo(Money.of(50));
    assertThat(to.balance()).isEqualTo(Money.of(0));
}
```

- AssertJ (`assertThat`) over raw JUnit asserts: the failure messages name the
  actual and expected values and the chain reads as a sentence.
- `@ParameterizedTest` with `@CsvSource` / `@MethodSource` for table cases.
- `@DisplayName` when the method name cannot carry the sentence.
- Prefer constructor injection and plain objects to `@MockBean`; a Spring
  context per test class is the main reason Java suites become slow.
- Testcontainers for a real database in integration tests — far more faithful
  than an in-memory substitute whose SQL dialect differs from production.
- Assert on state after the call, not on `verify(mock, times(1))`, unless the
  interaction itself is the requirement.
