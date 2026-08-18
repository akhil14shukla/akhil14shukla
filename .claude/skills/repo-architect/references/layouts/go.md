# Go layout

The idiomatic tree for a Go module, with the reasoning behind `internal/`,
`cmd/`, and the arguments about `pkg/`.

```
myservice/
├── go.mod  go.sum  Makefile  README.md
├── cmd/
│   ├── server/main.go       # one directory per binary; main() wires and starts
│   └── migrate/main.go
├── internal/                # compiler-enforced private to this module
│   ├── order/               # package per domain concept; the package name is
│   │   ├── order.go         # part of every call site, so keep it short
│   │   ├── service.go
│   │   └── service_test.go  # tests live beside the code
│   ├── postgres/            # adapters, named for the technology
│   └── http/                # transport
├── api/                     # OpenAPI/proto definitions
└── .github/workflows/ci.yml
```

Notes that save arguments: `internal/` is a real toolchain feature — code under
it cannot be imported outside the module. `pkg/` means nothing to the compiler,
the official layout guidance does not recommend it, and the widely-cited
`golang-standards/project-layout` is not an official Go standard. Start flat, add
`internal/` when you have something to hide, add `cmd/` when there is more than
one binary. Package names are lower-case and meaningful (`order`, not `models`)
because the caller writes `order.New()`.
