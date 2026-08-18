# pytest

The features that change how tests read in pytest, and the specific traps in
it.

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
