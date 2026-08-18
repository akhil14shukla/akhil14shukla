# Engineering skills

Seven skills that carry a consistent engineering standard into every coding
session, so it does not have to be re-typed as a prompt each time. They are
written to be usable by any model: concrete rules with the reasoning attached,
worked before/after examples, decision tables, and two executable scripts for
the parts that should be deterministic rather than recalled.

## The suite

Each skill owns one phase of the work and defers to the others rather than
repeating them, so only what is relevant loads into context.

| Skill | Owns | Loads when |
|---|---|---|
| **repo-architect** | Directory structure, module boundaries, import direction, config placement, safe restructuring | Starting a project, adding files to an unclear tree, "where does this go", "reorganise this repo" |
| **python-engineering** | Python: setup, typing, data modelling, idioms, CPython performance, errors, logging, concurrency | Any Python file is created or changed |
| **code-craft** | Any other language: naming, function shape, control flow, errors, state, dependencies, when to rewrite | Writing or refactoring TS/JS, Go, Rust, Java, C#, Ruby, shell, SQL |
| **testing-craft** | What to test, AAA structure, determinism, mocking discipline, edge cases, coverage as diagnostic | Writing, fixing, or reviewing tests |
| **perf-engineering** | Measure-first methodology, complexity, N+1 and I/O, caching, memory, benchmarking honestly | Something is slow, expensive, or memory-hungry |
| **docs-craft** | README, CONTRIBUTING, CHANGELOG, docstrings, ADRs, `docs/` by Diátaxis mode | Writing documentation, or finishing a project someone else will use |
| **ship-quality** | Self-review, running the repo's gates, security sweep, Conventional Commits, PR description, honest reporting | Before committing, before a PR, "is this ready" |

A typical project touches four of them in sequence: `repo-architect` to lay it
out, `python-engineering` or `code-craft` to write it, `testing-craft` alongside,
`docs-craft` and `ship-quality` to finish it.

## Bundled scripts

Two things that models reconstruct from memory badly, made deterministic:

```bash
# Generate a complete, correct starting tree (python | node | go | rust)
python repo-architect/scripts/scaffold.py --name my-project --lang python --kind app
python repo-architect/scripts/scaffold.py --name my-svc --lang go --kind service --dry-run

# Detect and run this repository's own format/lint/typecheck/test gates
./ship-quality/scripts/run_repo_checks.sh --list    # show what it would run
./ship-quality/scripts/run_repo_checks.sh           # run them, report each
```

`run_repo_checks.sh` never invents commands — it reads the Makefile,
`package.json` scripts, `pyproject.toml`, `go.mod`, and `Cargo.toml`, so what
passes locally is what CI runs.

## Installing

These are project skills: cloning this repository makes them available in
sessions started here. To use them everywhere, copy or symlink them into your
personal skills directory:

```bash
# Copy
cp -r .claude/skills/* ~/.claude/skills/

# Or symlink, so updates here propagate
for d in .claude/skills/*/; do
  [ -f "$d/SKILL.md" ] && ln -sfn "$(pwd)/${d%/}" ~/.claude/skills/
done
```

Claude loads a skill automatically when the work matches its description, or you
can invoke one directly: `/repo-architect`, `/python-engineering`, and so on.

## Structure

```
<skill>/
├── SKILL.md          the standing instructions — loaded when the skill triggers
├── references/       depth, loaded only when SKILL.md points at it
├── assets/           templates to fill in (docs-craft)
└── scripts/          executable, deterministic work
```

`SKILL.md` stays under ~400 lines so it is cheap to load; the detail lives in
`references/` and is read on demand. That split is what keeps seven skills
affordable to have installed at once.

## What these are opinionated about

- The reader of your code is a stranger under time pressure. Everything else
  follows from that.
- Structure is decided before the first file, and restructuring later is normal
  work, not a failure — done as mechanical, verifiable steps.
- Performance is measured, never guessed, and every optimisation carries the
  number that justified it.
- A test earns its place by failing when behaviour breaks, and only then.
- Documentation ships with the code, in the same commit, or it rots.
- "It runs" is not "it is done", and the report at the end says what was
  verified and what was skipped.
