# cargo test

The features that change how tests read in cargo test, and the specific traps
in it.

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
