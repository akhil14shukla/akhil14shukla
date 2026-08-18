# JUnit 5

The features that change how tests read in JUnit 5, and the specific traps in
it.

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
