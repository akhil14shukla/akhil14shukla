# Rust layout

The idiomatic tree for a Rust crate, and where unit tests, integration tests,
benchmarks, and examples each belong.

```
mycrate/
├── Cargo.toml  Cargo.lock          # lock committed for binaries; for libraries too, it is fine
├── src/
│   ├── main.rs                     # binary entry, thin
│   ├── lib.rs                      # library root: `pub mod` the public surface
│   ├── config.rs
│   └── orders/
│       ├── mod.rs                  # or orders.rs beside an orders/ dir (2018+ style)
│       ├── service.rs
│       └── model.rs
├── tests/                          # integration tests: use the crate as a consumer does
├── benches/                        # criterion benchmarks
└── examples/                       # compiled by CI, so they cannot rot
```

Unit tests live in-file under `#[cfg(test)] mod tests` — they can reach private
items, which is the point. `tests/` exercises only the public API, which is what
makes it a real contract check. A workspace (`[workspace] members = [...]`) is
the multi-crate form.
