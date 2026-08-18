---
name: repo-architect
description: Lay out a repository so a newcomer can predict where any file lives — directory structure, module boundaries, import direction, config and secrets placement, and the safe procedure for restructuring an existing mess without breaking it. Use this BEFORE writing the first file of any new project, script, package, service, CLI, or library, and whenever files are being added to an unclear tree, a flat pile of scripts needs organising, or someone says the repo is messy, hard to navigate, or needs restructuring. Trigger on "start a project", "set up a repo", "scaffold", "where should this file go", "reorganise/restructure this codebase", "split this into modules", or any first commit.
---

# Repository architecture

A repository is the first thing a new contributor reads, and they read it as a
tree before they read a single line of code. The test of a good layout: someone
who has never seen the project can guess where a given file lives, and be right.

The cost of getting this wrong is not aesthetic. A bad tree produces circular
imports, files nobody can safely delete, "utils" modules that everything depends
on, and a codebase where every change touches six directories. Those are
structural problems — no amount of clean code inside the files fixes them.

Structure is cheap to get right at file one and expensive to change at file
three hundred. **Spend five minutes on it before writing code.**

## Decide these five things first

You cannot lay out a project you cannot describe. Answer these before creating
any directory — out loud, to the user, in two or three sentences:

1. **What is this?** A library others import, an application that gets deployed,
   a CLI, a one-off analysis, or a monorepo of several? Each has a different
   correct shape, and the most common mistake is giving a small tool the layout
   of a large service.
2. **What are the two or three top-level concepts?** Not layers — *concepts*.
   "orders, payments, catalogue" for a shop; "ingest, transform, publish" for a
   pipeline. These become your top-level packages, and getting them from the
   problem domain rather than from a framework tutorial is what makes the tree
   survive.
3. **What crosses the boundary?** What is the public surface — the CLI commands,
   the HTTP routes, the exported functions? Everything else should be private
   and freely changeable.
4. **What is the entry point?** How does someone run this? There should be
   exactly one obvious answer, and it belongs at a predictable path.
5. **How does someone run the tests?** If the answer is not one command, fix
   that before writing code — it is the single biggest determinant of whether
   the project stays healthy.

If the project is a genuine one-off script that will be run once and deleted,
say so and write one well-named file with a docstring. Ceremony has a cost too.
Everything else gets a real structure, including "quick" tools — those are
exactly the ones that are still running in three years.

## The universal skeleton

Every serious repository, in every language, has these at the root. Missing
entries are not neutral; each one absent is a question every newcomer has to ask
someone.

```
project/
├── README.md              # what it is, how to run it, how to test it
├── LICENSE                # absent = nobody may legally use it
├── .gitignore             # language-appropriate, from the start
├── <manifest>             # pyproject.toml / package.json / go.mod / Cargo.toml
├── <lockfile>             # committed, always — reproducibility depends on it
├── .editorconfig          # so formatting does not depend on whose editor
├── CONTRIBUTING.md        # how to set up, test, and submit (once >1 person)
├── CHANGELOG.md           # for anything versioned or released
├── src/ or the language's convention   # the code
├── tests/                 # the tests
├── docs/                  # anything longer than the README warrants
├── scripts/               # dev/ops helper scripts, not application code
└── .github/workflows/     # CI: at minimum lint + type + test on every push
```

Config files live at the root, one per tool, and prefer the language's single
config file (`pyproject.toml`, `package.json`) over a scatter of dotfiles.
Somebody looking for "how is this linted" should find the answer in one place.

**Never commit**: secrets, `.env` with real values, credentials, API keys,
tokens, `node_modules`/`venv`/`target`, build output, `.DS_Store`, large binary
blobs, or personal IDE settings. Commit `.env.example` listing every variable
with a placeholder and a comment saying what it is — that file *is* the
configuration documentation, and its absence is why new contributors spend
their first day guessing.

## Organise by domain, not by kind

This is the decision that determines whether the tree still makes sense at file
three hundred.

```
# By kind — every feature is smeared across four directories.
src/
├── controllers/   order_controller, payment_controller, user_controller
├── services/      order_service, payment_service, user_service
├── models/        order, payment, user
└── utils/         everything else, imported by everything

# By domain — a feature is one directory, and you can read it, test it,
# move it, or delete it without a treasure hunt.
src/
├── orders/        routes, service, models, tests
├── payments/      routes, service, models, tests
├── users/         routes, service, models, tests
└── shared/        genuinely cross-cutting: config, errors, logging, db session
```

Why it matters concretely: to add a field to an order in the first tree you edit
four files in four directories and have to know that convention. In the second
you open one directory and everything relevant is in front of you. Deleting a
feature becomes `rm -rf src/orders`, which is the real test — if removing a
feature is hard, the boundaries are wrong.

**When layer-first is fine:** a project with one domain and under ~15 files, or
where the framework mandates it (Django apps, Rails). Do not fight a framework's
convention — inside a Django app, use its layout; the domain split happens at the
app level.

**`shared/` (or `common/`, `core/`) needs a rule or it becomes a landfill.**
Something belongs there only if two or more domains use it *and* it has no
domain meaning of its own — configuration, logging setup, error base classes,
the database session. A "shared" module that imports from a domain package is a
sign the code belongs in that domain.

**Never create a `utils` module.** It is a name that means "I did not decide
where this goes", and it becomes the file everything imports and nobody can
change. Name modules for what they contain: `text_formatting.py`,
`retry.py`, `csv_reader.go`. If a helper is used by exactly one module, it lives
in that module.

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

## Where a new file goes

Working rules that settle most arguments in seconds:

- **A file goes next to the code that uses it**, unless more than one domain
  uses it — then it moves up one level, no further.
- **Create a directory at the third related file, not the first.** Two files can
  sit beside each other. Premature directories are as bad as premature
  abstraction, and a directory containing one file is noise.
- **Depth beyond three or four levels below `src/` is a smell.**
  `src/a/b/c/d/e/thing.py` means the hierarchy is doing work that naming should
  do.
- **Tests mirror source**: `src/orders/pricing.py` → `tests/orders/test_pricing.py`.
  A reader must never have to search for the test of a file. (Where the language
  convention is co-located tests — Go's `_test.go`, Rust's `#[cfg(test)]`,
  frontends' `Component.test.tsx` — follow that instead; consistency with the
  ecosystem beats consistency with this document.)
- **One concept per file.** A file with three unrelated classes should be three
  files; a file with a class and its two small value objects is one file.
- **File names match what they contain**, in the language's casing convention:
  `snake_case.py`, `kebab-case.ts` or `PascalCase.tsx` for components,
  `lowercase.go`, `snake_case.rs`. Never `misc`, `helpers`, `stuff`, `temp`,
  `new_`, `v2`, or a person's name.

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

## Restructuring an existing repository

The user asking for this usually has working code in a bad tree. Moving it is
worth doing — but a restructure that breaks the build destroys trust in the
whole idea, so do it as a sequence of boring, verifiable steps.

**Read `references/restructuring.md` before starting.** The short version:

1. **Inventory first.** List every file and what it actually does. Note the
   entry points and anything that is dead — deleting dead code before moving it
   is the cheapest win available.
2. **Write down the target tree and get agreement on it** before moving
   anything. Show it to the user as a tree diagram.
3. **Establish a safety net.** If there are no tests, add a few
   characterisation tests over the main paths first. Without them you are not
   restructuring, you are rewriting blind.
4. **Move mechanically, in small commits.** `git mv` (history is preserved and
   the diff shows a rename), one coherent group per commit, imports fixed, tests
   green after each. Never mix a move with a behaviour change — a reviewer must
   be able to trust that a move is only a move.
5. **Fix imports with the toolchain**, not by hand: your IDE's move-refactor,
   `ruff check --fix`, `gofmt -r`, `ts-morph`. Hand-editing imports across 80
   files is where the typos come from.
6. **Delete the compatibility shims** you left behind, in a final commit, once
   nothing references them.

Say clearly what you are doing and why: "these 30 scripts are one pipeline, so
I am grouping them into `src/pipeline/{ingest,transform,publish}` and adding a
single entry point; behaviour is unchanged and the tests prove it." A silent
large-scale move is unreviewable.

## Scaffolding

`scripts/scaffold.py` generates a correct, complete starting tree so you do not
reconstruct one from memory (which is where missing `__init__.py` files,
forgotten `.gitignore` entries, and inconsistent naming come from):

```bash
python scripts/scaffold.py --name my-project --lang python --kind app --dir .
python scripts/scaffold.py --name my-svc --lang node --kind service --dry-run
```

`--lang`: `python`, `node`, `go`, `rust`. `--kind`: `lib`, `app`, `cli`,
`service`. It writes the manifest, source and test trees, `.gitignore`,
`.editorconfig`, a README skeleton, and a CI workflow that runs lint, types, and
tests. `--dry-run` prints the tree without writing. Review and adapt what it
produces — it is a correct starting point, not a finished project.

## References

- `references/layouts.md` — concrete, annotated trees per language and project
  type: Python (lib/CLI/service/data), TypeScript (node service, React app,
  monorepo), Go, Rust, and Java. Read the one you are building.
- `references/restructuring.md` — the full step-by-step procedure for
  reorganising an existing codebase safely, including how to split a large
  module, break an import cycle, and stage the commits.

Related: `docs-craft` for the README, ADRs, and documentation set that belong in
the tree; `ship-quality` for the CI gates that keep it honest.
