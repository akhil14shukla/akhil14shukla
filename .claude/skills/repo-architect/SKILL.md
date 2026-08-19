---
name: repo-architect
description: Lay out a repository so a newcomer can predict where any file lives — directory structure, module boundaries, import direction, config and secrets placement, and restructuring an existing mess safely. Use BEFORE writing the first file of any new project, script, package, service, CLI, or library, and whenever files are being added to an unclear tree or someone says the repo is messy or needs reorganising. Trigger on "start a project", "set up a repo", "scaffold", "where should this file go", "restructure this codebase", "split this into modules", or any first commit.
---

# Repository architecture

A newcomer reads the tree before they read a line of code. The test of a good
layout: someone who has never seen the project can guess where a given file
lives, and be right.

Getting this wrong is structural, not cosmetic — it produces circular imports,
files nobody can safely delete, a `utils` module everything depends on, and
changes that touch six directories. Clean code inside the files does not fix any
of that. It is cheap at file one and expensive at file three hundred, so **spend
five minutes on it before writing code.**

## Decide these first

Answer out loud, in two or three sentences, before creating any directory:

1. **What is this** — a library, a deployed application, a CLI, a one-off
   analysis, a monorepo? The most common mistake is giving a small tool the
   layout of a large service.
2. **What are the two or three top-level concepts?** Take them from the problem
   domain ("orders, payments, catalogue"), not from a framework tutorial. These
   become your top-level packages and are what make the tree survive.
3. **What is the public surface** — the CLI commands, the routes, the exported
   functions? Everything else stays private and freely changeable.
4. **What is the entry point, and how do you run the tests?** If the test answer
   is not one command, fix that before writing code; it is the single biggest
   determinant of whether the project stays healthy.

A genuine one-off script gets one well-named file with a docstring — ceremony
has a cost too. Everything else gets a real structure, including "quick" tools,
which are exactly the ones still running in three years.

## Check what is current before you choose

**Your knowledge of the ecosystem has a cutoff; the ecosystem does not.** Picking
a framework from memory is how a project starts on a version that went
end-of-life eight months ago, or adopts a library the maintainer archived.

**Search the web before locking in** a runtime version, framework, ORM, auth
library, datastore, build tool, deployment target, or any dependency that will
be hard to remove. Establish four things — current stable version and the EOL of
the one you would otherwise pick, whether it is still maintained, whether this is
still the recommended approach, and any open security advisories — and confirm
them against the primary source rather than a blog post. Then **state what you
verified and when**, so a future reader knows whether to re-check.

Skip it for things that do not move: a standard-library function, an established
pattern, SQL semantics. `references/architecture-decisions.md` has the full
method and the rest of the architecture decisions.

## The universal skeleton

```
project/
├── README.md                  what it is, how to run it, how to test it
├── LICENSE                    absent = nobody may legally use it
├── <manifest> + <lockfile>    lockfile committed, always
├── .env.example               every variable, placeholder + comment
├── .gitignore  .editorconfig
├── src/  tests/  docs/  scripts/
└── .github/workflows/         at minimum lint + type + test on every push
```

Each missing entry is a question every newcomer has to ask someone. **Never
commit** secrets, real `.env` files, credentials, build output, dependency
directories, or personal IDE settings.

## Organise by domain, not by kind

The one decision that determines whether the tree still makes sense at file
three hundred.

```
src/orders/     routes, service, models, tests   ← a feature is ONE directory
src/payments/   routes, service, models, tests
src/shared/     config, db, logging, errors      ← genuinely cross-cutting only

# not: controllers/ services/ models/ utils/     ← every feature smeared across
#      four directories, plus one landfill
```

The real test: deleting a feature should be `rm -rf src/orders`. If that is
hard, the boundaries are wrong. Layer-first is fine for a single-domain project
under ~15 files, or where a framework mandates it — do not fight Django or Rails
conventions; the domain split happens at the app level there.

**Never create a `utils` module.** It means "I did not decide where this goes",
and becomes the file everything imports and nobody can change. A helper used by
one module lives in that module.

## Where a new file goes

Next to the code that uses it; up one level only if two domains use it. **Create
a directory at the third related file, not the first.** Tests mirror source
unless the ecosystem co-locates them. Never name a file `misc`, `helpers`,
`stuff`, `temp`, `new_`, or `v2`. The full placement rules are in
`references/layouts.md`.

## Scaffolding

Do not reconstruct a tree from memory — that is where missing `__init__.py`
files, incomplete `.gitignore`s, and inconsistent naming come from:

```bash
python scripts/scaffold.py --name my-project --lang python --kind app
python scripts/scaffold.py --help     # --lang python|node|go|rust, --kind lib|app|cli|service
```

It writes the manifest, source and test trees, `.gitignore`, `.editorconfig`,
README skeleton, and a CI workflow that runs lint, types, and tests. `--dry-run`
prints without writing. Review and adapt — a correct starting point, not a
finished project.

## Read the reference that matches your task

| If you are… | Read |
|---|---|
| Choosing a stack, deciding one service or several, picking an API style or datastore | `references/architecture-decisions.md` |
| Building a specific kind of project, or placing a new file | `references/layouts.md` — read only the tree that matches |
| Deciding what may import what, where config and secrets live, or monorepo vs not | `references/boundaries-and-config.md` |
| Reorganising an existing codebase, splitting a large module, or breaking an import cycle | `references/restructuring.md` |

Adjacent skills: `docs-craft` for the README and ADRs that belong in the tree,
`ship-quality` for the CI gates that keep it honest.
