# Import direction, configuration, and monorepos

Read this when deciding what may import what, where configuration and secrets
live, or whether several things belong in one repository.

## Import direction

Dependencies must point one way, and the direction must be stated. The
conventional and well-tested one:

```
entry point / transport  →  application logic  →  domain  →  (nothing)
     (cli, http, jobs)         (use cases)        (types, rules)
                    ↘  infrastructure (db, http clients, queues)  ↗
                             implements interfaces the domain defines
```

Two rules follow, and they are worth enforcing mechanically:

- **The domain imports nothing from the outer rings.** No framework, no ORM
  model, no `request` object in a pricing rule. That is what lets you test the
  rules in milliseconds with no fixtures, and what stops a framework upgrade
  from touching your business logic.
- **No cycles, ever.** A circular import is a design error that the toolchain
  happens to report as a build error. Fixing it by moving an import inside a
  function hides the problem; the real fix is that one of the two modules should
  not know about the other — usually by extracting the shared type downward, or
  by inverting the dependency behind an interface.

Enforce privacy with the language's mechanism, not a comment: Go's `internal/`,
Rust's `pub(crate)`, Java's package-private, a leading underscore plus
`__all__` in Python, `"exports"` in `package.json`.

## Configuration and secrets

- **Configuration comes from the environment; secrets never live in the repo.**
  Load and validate all of it in exactly one module, at startup, into a typed
  object. Then the rest of the code reads a field rather than
  `os.environ["THING"]` scattered across twenty files where a missing variable
  surfaces as a `KeyError` two hours into a job.
- **Fail at startup on missing or invalid config**, with a message naming the
  variable. Discovering a bad config value at 3am on the first request is the
  avoidable version of this problem.
- Keep environment differences to *values*, not code paths. `if env ==
  "production"` scattered through the codebase means production is untested.
- `.env.example` is committed and complete; `.env` is git-ignored.

## Monorepo or not

One repository per independently deployable thing is the default. Choose a
monorepo when several packages change together and share types — then make the
boundaries explicit:

```
repo/
├── apps/          deployables. May import from packages/. Never from each other.
├── packages/      shared libraries. May import other packages/. Never apps/.
└── <workspace config>   pnpm-workspace.yaml / uv workspace / go.work / Cargo workspace
```

That import rule is the whole value of the structure; without it you have a
folder full of code with hidden coupling. Enforce it with a lint rule or a
dependency-check step in CI, because it will otherwise be violated within a
month.
