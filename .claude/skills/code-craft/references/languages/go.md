# Go

The rules that separate code a maintainer trusts from code that merely runs in Go, plus the footguns that cause real production bugs.

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
