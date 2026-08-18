# C#

The rules that separate code a maintainer trusts from code that merely runs in C#, plus the footguns that cause real production bugs.

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
