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

## The universal skeleton

```
project/
├── README.md              what it is, how to run it, how to test it
├── LICENSE                absent = nobody may legally use it
├── .gitignore  .editorconfig
├── <manifest> + <lockfile>    committed, always
├── .env.example           every variable, with a placeholder and a comment
├── src/ (or the language's convention)
├── tests/                 mirroring src/
├── docs/  scripts/
└── .github/workflows/     at minimum lint + type + test on every push
```

Each missing entry is a question every newcomer has to ask someone. **Never
commit** secrets, real `.env` files, credentials, build output, dependency
directories, or personal IDE settings.

## Organise by domain, not by kind

This one decision determines whether the tree still makes sense at file three
hundred.

```
src/orders/     routes, service, models, tests      ← a feature is one directory
src/payments/   routes, service, models, tests
src/shared/     config, db, logging, errors         ← genuinely cross-cutting only

# not: controllers/  services/  models/  utils/     ← every feature smeared
#      across four directories, and one landfill
```

The real test: deleting a feature should be `rm -rf src/orders`. If removing one
is hard, the boundaries are wrong. Layer-first is fine for a single-domain
project under ~15 files, or where a framework mandates it — do not fight Django
or Rails conventions; the domain split happens at the app level there.

**Never create a `utils` module.** It means "I did not decide where this goes",
and it becomes the file everything imports and nobody can change. Name modules
for what they contain. A helper used by exactly one module lives in that module.

## Where a new file goes

- Next to the code that uses it; if two domains use it, up one level, no further.
- **Create a directory at the third related file, not the first.**
- Depth past three or four levels below `src/` means the hierarchy is doing work
  that naming should do.
- Tests mirror source, so a reader never has to search for a file's test —
  unless the ecosystem co-locates them (Go, Rust, frontend components), in which
  case follow the ecosystem.
- File names match their contents in the language's casing convention. Never
  `misc`, `helpers`, `stuff`, `temp`, `new_`, or `v2`.

## Scaffolding

Do not reconstruct a tree from memory — that is where missing `__init__.py`
files, incomplete `.gitignore`s, and inconsistent naming come from:

```bash
python scripts/scaffold.py --name my-project --lang python --kind app
python scripts/scaffold.py --name my-svc --lang go --kind service --dry-run
```

`--lang`: `python|node|go|rust`. `--kind`: `lib|app|cli|service`. Writes the
manifest, source and test trees, `.gitignore`, `.editorconfig`, README skeleton,
and a CI workflow. Review and adapt it — a correct starting point, not a
finished project.

## Read the reference that matches your task

| If you are… | Read |
|---|---|
| Building a specific kind of project and want the annotated tree | `references/layouts.md` |
| Deciding what may import what, where config and secrets live, or monorepo vs not | `references/boundaries-and-config.md` |
| Reorganising an existing codebase, splitting a large module, or breaking an import cycle | `references/restructuring.md` |

Adjacent skills: `docs-craft` for the README and ADRs that belong in the tree,
`ship-quality` for the CI gates that keep it honest.
