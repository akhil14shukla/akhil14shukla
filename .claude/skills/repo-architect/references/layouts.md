# Concrete repository layouts

Annotated trees for the common cases. Copy the one that matches, then adapt —
the comments explain *why* each piece is where it is, so you can make informed
deviations rather than cargo-culting.

## Contents

- [Placing a new file](#placing-a-new-file)
- [Python: library](#python-library)
- [Python: CLI tool](#python-cli-tool)
- [Python: web service](#python-web-service)
- [Python: data / ML project](#python-data--ml-project)
- [TypeScript: Node service](#typescript-node-service)
- [TypeScript: React application](#typescript-react-application)
- [TypeScript: monorepo](#typescript-monorepo)
- [Go](#go)
- [Rust](#rust)
- [Java / Kotlin](#java--kotlin)

## Placing a new file

Working rules that settle most arguments in seconds:

- **A file goes next to the code that uses it**, unless more than one domain
  uses it — then it moves up one level, no further.
- **Create a directory at the third related file, not the first.** Two files can
  sit beside each other; a directory containing one file is noise, and premature
  directories are as bad as premature abstraction.
- **Depth beyond three or four levels below `src/` is a smell.**
  `src/a/b/c/d/e/thing.py` means the hierarchy is doing work that naming should
  do.
- **Tests mirror source**: `src/orders/pricing.py` → `tests/orders/test_pricing.py`,
  so a reader never has to search for a file's test. Where the ecosystem
  co-locates tests instead — Go's `_test.go`, Rust's `#[cfg(test)]`, a frontend's
  `Component.test.tsx` — follow the ecosystem; consistency with it beats
  consistency with this document.
- **One concept per file.** Three unrelated classes should be three files; a
  class plus its two small value objects is one file.
- **File names match what they contain**, in the language's casing convention:
  `snake_case.py`, `kebab-case.ts` or `PascalCase.tsx` for components,
  `lowercase.go`, `snake_case.rs`. Never `misc`, `helpers`, `stuff`, `temp`,
  `new_`, `v2`, or a person's name.

---

## Python: library

```
mylib/
├── pyproject.toml           # metadata, deps, and every tool's config
├── uv.lock                  # committed
├── README.md  LICENSE  CHANGELOG.md  .gitignore  .editorconfig
├── src/
│   └── mylib/
│       ├── __init__.py      # the public API: import and re-export, define __all__
│       ├── py.typed         # marks the package as typed so consumers get checking
│       ├── _internal.py     # leading underscore = private, freely changeable
│       ├── models.py
│       └── errors.py        # one exception hierarchy, exported from __init__
├── tests/
│   ├── conftest.py          # shared fixtures
│   └── test_models.py
├── docs/
└── .github/workflows/ci.yml
```

`src/` is not optional for a library: without it, tests import the source
directory rather than the installed package, so packaging bugs (a missing
module, an uncommitted data file) ship undetected. `py.typed` is what makes your
annotations visible to consumers — without it they get `Any` for your whole API.

`__init__.py` is your API contract. Import the names you intend people to use
and list them in `__all__`; everything else stays private and can change without
a major version.

## Python: CLI tool

```
mytool/
├── pyproject.toml           # [project.scripts] mytool = "mytool.cli:main"
├── src/mytool/
│   ├── __init__.py
│   ├── cli.py               # argument parsing and exit codes ONLY
│   ├── commands/            # one module per subcommand
│   │   ├── build.py
│   │   └── deploy.py
│   ├── core/                # the actual logic — importable, testable, no argparse
│   └── config.py            # load + validate config in one place
└── tests/
```

The separation that matters: `cli.py` translates argv into typed arguments and
calls into `core/`. Because `core/` knows nothing about argparse, it is testable
without subprocesses and reusable as a library. `main()` returns an exit code
and is invoked by `raise SystemExit(main())`.

## Python: web service

```
myservice/
├── pyproject.toml  docker-compose.yml  Dockerfile  .env.example
├── src/myservice/
│   ├── main.py              # app factory + wiring only; no business logic
│   ├── config.py            # env → typed settings object, validated at startup
│   ├── orders/              # a domain: everything about orders lives here
│   │   ├── router.py        # HTTP layer: parse, validate, call service, respond
│   │   ├── service.py       # use cases — the only place business rules live
│   │   ├── models.py        # domain types
│   │   ├── schemas.py       # request/response shapes (pydantic) — boundary only
│   │   └── repository.py    # persistence for this domain
│   ├── payments/            # same shape
│   └── shared/
│       ├── db.py  logging.py  errors.py  middleware.py
├── migrations/              # versioned, forward-only, reviewed
├── tests/
│   ├── unit/                # fast, no I/O
│   └── integration/         # real database, marked so they can be skipped locally
└── .github/workflows/ci.yml
```

`router.py` contains no `if` about business meaning. `service.py` contains no
`Request`/`Response`. That line is what lets you test pricing rules without
booting a web server, and it is the first thing to check in review.

## Python: data / ML project

```
project/
├── pyproject.toml
├── README.md                # what question this answers, and how to reproduce it
├── data/                    # ALL git-ignored except the schema/README
│   ├── raw/                 # immutable; never write here after download
│   ├── interim/
│   └── processed/
├── notebooks/               # exploration only, numbered: 01-explore-signups.ipynb
├── src/project/
│   ├── data/                # loading + cleaning, importable by notebooks
│   ├── features/
│   ├── models/              # train.py, predict.py, evaluate.py
│   └── pipeline.py          # the reproducible end-to-end run
├── configs/                 # experiment configs, versioned
├── tests/
└── models/                  # serialised artefacts, git-ignored (DVC/S3/registry)
```

The rule that makes data projects reproducible: **notebooks import from `src/`,
never the reverse, and no logic lives only in a notebook.** A notebook is a lab
notebook — a record of exploration. The moment a transformation matters, it moves
into `src/` where it can be tested and re-run. Raw data is immutable; every
derived artefact must be regenerable by running the pipeline, and the README
must say exactly how.

---

## TypeScript: Node service

```
service/
├── package.json  pnpm-lock.yaml  tsconfig.json  .env.example
├── src/
│   ├── index.ts             # composition root: build deps, start server
│   ├── config.ts            # env parsed + validated with zod, exported typed
│   ├── orders/
│   │   ├── orders.routes.ts
│   │   ├── orders.service.ts
│   │   ├── orders.repository.ts
│   │   ├── orders.types.ts
│   │   └── orders.test.ts
│   └── shared/  db.ts  logger.ts  errors.ts  http.ts
├── tests/                   # integration/e2e; unit tests sit beside their source
└── .github/workflows/ci.yml
```

Co-locate unit tests with source (`orders.service.test.ts`) — a file and its test
move together, and an untested file is visible at a glance. Keep integration
tests separate since they need infrastructure.

## TypeScript: React application

```
app/
├── src/
│   ├── main.tsx  App.tsx
│   ├── features/            # by feature, each self-contained
│   │   └── checkout/
│   │       ├── CheckoutPage.tsx
│   │       ├── components/  PaymentForm.tsx
│   │       ├── hooks/       useCheckout.ts
│   │       ├── api.ts
│   │       └── types.ts
│   ├── components/          # genuinely generic, no domain knowledge: Button, Modal
│   ├── lib/                 # framework-agnostic helpers (formatting, http client)
│   ├── hooks/               # generic hooks used across features
│   └── styles/
└── tests/e2e/
```

The distinction that keeps this clean: `components/` may not import from
`features/`. If a "generic" component knows what an order is, it belongs in that
feature. A feature directory should be deletable in one command.

## TypeScript: monorepo

```
repo/
├── pnpm-workspace.yaml  turbo.json  tsconfig.base.json
├── apps/
│   ├── web/                 # may import packages/*, never apps/*
│   └── api/
├── packages/
│   ├── ui/                  # may import packages/*, never apps/*
│   ├── domain/              # shared types and business rules — no framework code
│   └── config/              # shared eslint/tsconfig/prettier presets
└── .github/workflows/ci.yml
```

Use workspace protocol references (`"@repo/domain": "workspace:*"`) and
TypeScript project references so builds are incremental and the dependency graph
is explicit. Enforce the "apps never import apps" rule in CI — it is the only
thing standing between a monorepo and a distributed monolith.

---

## Go

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

## Rust

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

## Java / Kotlin

```
service/
├── build.gradle.kts  settings.gradle.kts  gradle/libs.versions.toml
├── src/
│   ├── main/
│   │   ├── java/com/company/service/
│   │   │   ├── Application.java
│   │   │   ├── order/            # package per domain, not per layer
│   │   │   │   ├── OrderController.java
│   │   │   │   ├── OrderService.java
│   │   │   │   ├── OrderRepository.java
│   │   │   │   └── Order.java
│   │   │   └── shared/config/  shared/error/
│   │   └── resources/  application.yml  db/migration/
│   └── test/java/com/company/service/order/OrderServiceTest.java
```

Package-by-feature (`order/`) rather than package-by-layer
(`controllers/`, `services/`) gives you package-private visibility as a real
boundary: `OrderRepository` can be package-private and genuinely unreachable from
other features. Use the version catalogue (`libs.versions.toml`) so dependency
versions live in one place.
