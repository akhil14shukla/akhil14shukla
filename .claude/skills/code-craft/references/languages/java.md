# Java / Kotlin

The rules that separate code a maintainer trusts from code that merely runs in Java / Kotlin, plus the footguns that cause real production bugs.

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
