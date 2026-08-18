# Rust

The rules that separate code a maintainer trusts from code that merely runs in Rust, plus the footguns that cause real production bugs.

**Let the type system carry the invariants; that is what you are paying for.**

- Return `Result<T, E>` for recoverable failure, `Option<T>` for absence.
  `unwrap()`/`expect()` in library code is a landmine — acceptable in tests,
  in `main`, and where you can prove it cannot fail (say so in the `expect`
  message: `expect("regex is a compile-time constant")`).
- Define one error enum per crate/module with `thiserror`; use `anyhow` only in
  binaries and tests where the caller will not match on the variant. `?` for
  propagation.
- Newtypes are cheap and eliminate whole bug classes: `struct UserId(u64)`
  cannot be passed where `OrderId` is expected.
- Take `&str`/`&[T]` as parameters, return owned `String`/`Vec<T>`. Clone
  deliberately when it simplifies the code — a clone in a cold path is not a
  performance problem, and fighting the borrow checker with `Rc<RefCell<_>>`
  usually signals a design that wants restructuring instead.
- Prefer iterator chains to index loops: bounds checks disappear and intent is
  explicit.
- `#![forbid(unsafe_code)]` unless you have a specific need; each `unsafe` block
  carries a `// SAFETY:` comment stating the invariant you are upholding.
- Derive `Debug` on public types; `Clone`/`Copy` only where cheap and meaningful.

**Tooling baseline**: `cargo fmt`, `cargo clippy -- -D warnings`, `cargo test`,
`cargo deny` for licences and advisories.
