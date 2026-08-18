# Per-language rules that actually matter

Read only the section for the language you are writing. Each section lists the
choices that separate code a maintainer trusts from code that merely runs, plus
the footguns that cause real production bugs in that language.

## Contents

- [TypeScript / JavaScript](#typescript--javascript)
- [Go](#go)
- [Rust](#rust)
- [Java / Kotlin](#java--kotlin)
- [C#](#c)
- [Ruby](#ruby)
- [Shell (bash)](#shell-bash)
- [SQL](#sql)

---

## TypeScript / JavaScript

**Use TypeScript, in strict mode.** `"strict": true` plus
`noUncheckedIndexedAccess` and `exactOptionalPropertyTypes` in `tsconfig.json`.
Without `noUncheckedIndexedAccess`, `arr[i]` is typed as `T` even when the index
is out of bounds, and the type system actively lies to you about the most common
source of runtime `undefined`.

**Types**

- Never `any`. Use `unknown` at boundaries and narrow it — `unknown` forces the
  check, `any` silently disables the compiler for everything downstream.
- Prefer discriminated unions over optional fields for state:
  ```ts
  // Lets you construct a "success" with an error attached.
  type Result = { ok: boolean; value?: User; error?: Error };

  // The impossible states no longer typecheck.
  type Result =
    | { ok: true; value: User }
    | { ok: false; error: Error };
  ```
- `type` for unions and function shapes, `interface` for object contracts that
  others implement or augment. Do not churn a codebase to convert between them.
- Derive, don't duplicate: `keyof`, `typeof`, `Pick`, `Omit`, `ReturnType`,
  and `as const` keep types in sync with the values they describe.
- Validate external data at the edge with a schema library (zod, valibot) and
  infer the type from the schema. A hand-written `interface` over an API
  response is a claim, not a check — the moment the API changes, your types are
  fiction.
- `satisfies` when you want a value checked against a type without widening it.

**Runtime and async**

- `===` always. `==` only for the deliberate `x == null` null-or-undefined check.
- `async`/`await` over `.then()` chains; mixing them in one function is how
  unhandled rejections appear. Every `await` that can reject is inside a `try`
  or is deliberately propagated.
- `Promise.all` rejects on the first failure and abandons the rest — use
  `Promise.allSettled` when you need every outcome. Never `await` inside a loop
  when the iterations are independent; collect promises and await once.
- A floating promise (calling an async function without awaiting or catching) is
  a crash waiting for the right timing. Enable
  `@typescript-eslint/no-floating-promises`.
- `structuredClone` for deep copies; the `JSON.parse(JSON.stringify(x))` idiom
  silently destroys `Date`, `Map`, `Set`, `undefined`, and `BigInt`.
- Money is never a `number`. IEEE-754 makes `0.1 + 0.2 !== 0.3`; use integer
  minor units or a decimal library.

**Modules**

- Named exports over default exports: they rename consistently, autocomplete,
  and survive refactors.
- Wide barrel files (`index.ts` re-exporting everything) wreck tree-shaking and
  create import cycles. A barrel at a *feature's* root exposing that feature's
  public surface is fine and useful; a repo-wide `src/index.ts` is not.
- Node built-ins get the `node:` prefix (`import fs from "node:fs/promises"`) so
  the intent is unambiguous and no npm package can shadow them.

**Tooling baseline**: TypeScript strict, ESLint (typescript-eslint), Prettier or
Biome, Vitest or Jest, and one package manager committed with its lockfile.

---

## Go

**Errors are values, and the wrapping chain is the debugging tool.**

```go
if err != nil {
    return fmt.Errorf("fetch user %d: %w", id, err)   // %w preserves the cause
}
```

- Every wrap adds *the operation and its inputs*, lower-case, no trailing
  punctuation — they concatenate into a readable trail.
- `errors.Is` for sentinel comparison, `errors.As` for typed extraction. Never
  compare error strings.
- Never `_ = err`. If ignoring is correct, write why on that line.
- `panic` is for programmer bugs and unrecoverable init, never for expected
  failure paths crossing a package boundary.

**Idioms**

- Accept interfaces, return structs. Define the interface in the *consuming*
  package, keep it to the one or two methods that package actually uses.
- `context.Context` is the first parameter of anything that does I/O, and it is
  passed down, never stored in a struct.
- `defer` cleanup immediately after successful acquisition. Remember `defer` in
  a loop runs at function exit — that is a file-descriptor leak; extract the
  body into a function.
- Zero values should be useful: a struct usable as `var b bytes.Buffer` beats
  one that requires `NewX()` before it works.
- Preallocate when the size is known: `make([]T, 0, n)`.
- A slice from `s[:k]` shares the original backing array — copy explicitly when
  the parent must be released or must not be mutated.
- Loop-variable capture in goroutines is fixed as of Go 1.22, but be explicit
  where it aids the reader.
- `sync.WaitGroup` for fan-out, `errgroup.Group` when any worker can fail (it
  gives you first-error and cancellation for free).

**Layout**: `internal/` is enforced by the toolchain and is the right way to
keep packages private. `pkg/` means nothing to the compiler and the Go team does
not recommend it. Package names are short, lower-case, no underscores, and never
`util` — the package name is part of every call site (`user.New`, not
`user.NewUser`).

**Tooling baseline**: `gofmt` (non-negotiable), `go vet`, `staticcheck`,
`golangci-lint`, `go test -race` in CI.

---

## Rust

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

---

## Java / Kotlin

- **Never return `null` from a public API.** `Optional<T>` for Java,
  non-nullable types with explicit `?` in Kotlin. `null` as "no result" is the
  most expensive default in the language's history.
- Immutable by default: `final` fields, `record` types (Java 16+), `val` and
  `data class` in Kotlin. Return unmodifiable views from getters, or copies.
- Constructor injection, not field injection. It makes dependencies visible,
  allows `final`, and works without a framework in tests.
- Checked vs unchecked: throw unchecked for programmer errors, checked (or a
  result type) only where the caller has a genuine recovery path. Never
  `catch (Exception e)` at a layer that cannot handle it.
- `try-with-resources` for anything `Closeable`. Manual `finally` blocks leak.
- `equals`/`hashCode` always together, and immutably — mutating a field used in
  `hashCode` after inserting into a `HashMap` loses the entry.
- Streams for transformation pipelines, plain loops when a stream needs
  side effects or nested state. A `forEach` with mutation is a loop wearing a
  costume.
- Kotlin: prefer `sealed interface` + `when` for closed state, extension
  functions over util classes, coroutines with a structured `CoroutineScope`
  (never `GlobalScope`).

**Tooling baseline**: Spotless/ktlint, ErrorProne or Detekt, JUnit 5 with
AssertJ, JaCoCo as a diagnostic.

---

## C#

- Nullable reference types on (`<Nullable>enable</Nullable>`) and warnings as
  errors for nullability. It is the single highest-value switch in the language.
- `record` for value semantics, `readonly struct` for small immutable values,
  `sealed` by default on classes not designed for inheritance.
- `async` all the way down; never `.Result` or `.Wait()` — that is the classic
  deadlock. Return `Task`, not `void`, except for event handlers. Pass
  `CancellationToken` through and honour it.
- `IEnumerable<T>` is lazy: enumerating twice re-runs the query. Materialise
  with `ToList()` when you will iterate more than once, and never return a
  live LINQ-to-DB query across a layer boundary.
- `using` declarations for disposables; implement `IAsyncDisposable` when
  cleanup is async.
- `IOptions<T>` for configuration, DI via the built-in container, `ILogger<T>`
  with structured message templates (`"Charged {OrderId}"`, not interpolation).

---

## Ruby

- Small methods, meaningful names, and `frozen_string_literal: true` at the top
  of every file.
- Prefer keyword arguments for anything with more than one parameter — Ruby
  call sites are otherwise unreadable.
- `Struct`/`Data.define` for value objects rather than passing hashes around;
  a hash with string keys crossing three methods is an undocumented type.
- Rescue specific error classes. A bare `rescue` catches `StandardError` and
  hides real bugs; `rescue Exception` also catches interrupts and is almost
  always wrong.
- Guard clauses and `return` early; avoid `unless` with a compound condition.
- Rails: keep controllers thin (params → service → response), push logic into
  POROs or service objects rather than fat models, and always paginate.
  `includes` to kill N+1 queries — see `perf-engineering`.

**Tooling baseline**: RuboCop, RSpec or Minitest, Sorbet or RBS if the codebase
is large.

---

## Shell (bash)

Shell is where "quick script" becomes an outage. If it exceeds ~100 lines or
needs data structures, rewrite it in Python or Go — that is not a failure, it
is the correct call.

```bash
#!/usr/bin/env bash
set -euo pipefail          # exit on error, undefined var, and failed pipe stage
IFS=$'\n\t'
```

- **Quote every expansion**: `"$var"`, `"$@"`, `"${arr[@]}"`. An unquoted
  variable containing a space becomes two arguments, and one containing `*`
  becomes your entire directory listing.
- `[[ ]]` over `[ ]`; `$(...)` over backticks.
- Check that required commands and variables exist up front, with a clear error,
  rather than failing halfway through with a cryptic message.
- Use `mktemp -d` for scratch space and `trap 'rm -rf "$tmp"' EXIT` to clean up
  on every exit path, including failure.
- Never `rm -rf "$dir/"*` without verifying `$dir` is non-empty and is what you
  think — this is the classic data-loss bug.
- `set -e` does not fire inside `if`, `&&`, or a function whose result is
  tested; check exit codes explicitly where it matters.
- Run **ShellCheck**. It catches most of the above mechanically.

---

## SQL

- **Never build a query by string concatenation with user input.** Parameterised
  queries only — this is SQL injection, still the most exploited class of web
  vulnerability.
- Name every column you select. `SELECT *` breaks when a column is added,
  transfers data you do not use, and hides which index would help.
- Every query that can return many rows has a `LIMIT` and a deterministic
  `ORDER BY`. Pagination without a stable sort silently returns duplicates and
  skips rows.
- Index the columns you filter, join, and sort on — and know that a leading
  wildcard `LIKE '%x'` and a function applied to a column (`WHERE lower(email)`)
  both prevent index use unless you add a matching expression index.
- Read the `EXPLAIN ANALYZE` output before declaring a query fast. A sequential
  scan on a 200-row table in dev is a sequential scan on 20M rows in production.
- Keep transactions short and never hold one open across a network call to
  another service; that is how connection pools exhaust.
- Migrations are forward-only, reviewed, and tested against production-sized
  data. Adding a column with a default, adding an index, or changing a type can
  each lock a large table — check the semantics for your engine and version, and
  use the concurrent/online variant.
- Put schema constraints in the schema: `NOT NULL`, foreign keys, `CHECK`,
  unique indexes. Application-level validation alone always drifts.
