# Engineering skills

Nine skills that carry a consistent engineering standard into every coding
session, so it does not have to be re-typed as a prompt each time. They are
written to be usable by any model: concrete rules with the reasoning attached,
worked before/after examples, decision tables, and executable scripts for the
parts that should be deterministic rather than recalled.

They are built for progressive disclosure: a skill triggering costs about 1,000
tokens, not 4,000, because the depth lives in references that load only when the
task actually needs them. See [Context cost](#context-cost).

**Only two skills are language-scoped** — `python-engineering` for Python, and
`code-craft` for every other language. Language detail lives in references
inside those two, never as separate skills, so the listing stays small and there
is exactly one place to look per language.

## The suite

Each skill owns one phase of the work and defers to the others rather than
repeating them, so only what is relevant loads.

| Skill | Owns | Loads when |
|---|---|---|
| **codebase-recon** | Finding your way around unfamiliar code without burning context — search before read, read ranges, trace one path | Before editing a repo you have not read; "how does X work here", "where is Y handled" |
| **repo-architect** | Directory structure, module boundaries, import direction, config placement, architecture decisions, safe restructuring | Starting a project, "where does this go", "restructure this repo", choosing a stack |
| **python-engineering** | Python: setup, typing, data modelling, idioms, CPython performance, errors, logging, concurrency | Any Python file is created or changed |
| **code-craft** | Any other language: naming, function shape, control flow, errors, state, when to rewrite | Writing or refactoring TS/JS, Go, Rust, Java, C#, Ruby, shell, SQL |
| **testing-craft** | What to test, AAA structure, determinism, mocking discipline, edge cases, coverage as diagnostic | Writing, fixing, or reviewing tests |
| **perf-engineering** | Measure-first method, design-time performance, complexity, N+1 and I/O, caching, memory, cost | Something is slow, expensive, or memory-hungry; designing something whose speed matters |
| **ground-truth-analysis** | Comparing numbers against a reference: the comparison contract, layered checks, hypotheses and their tests, adversarial review, the closing bridge | "do these match", reconciling a sheet or export against a source of truth, explaining why totals disagree |
| **docs-craft** | README, CONTRIBUTING, CHANGELOG, docstrings, ADRs, `docs/` by Diátaxis mode | Writing documentation, or finishing something someone else will use |
| **ship-quality** | Self-review, running the repo's gates, security sweep, Conventional Commits, PR description, honest reporting | Before committing, before a PR, "is this ready" |

A typical project touches four in sequence: `codebase-recon` or `repo-architect`
to orient, `python-engineering` or `code-craft` to write, `testing-craft`
alongside, `ship-quality` to finish.

## Bundled scripts

Five things that are reconstructed from memory badly, made deterministic:

```bash
# Generate a complete, correct starting tree (python | node | go | rust)
python repo-architect/scripts/scaffold.py --name my-project --lang python --kind app

# Detect and run THIS repository's own format/lint/typecheck/test gates
./ship-quality/scripts/run_repo_checks.sh --list    # show what it would run
./ship-quality/scripts/run_repo_checks.sh           # run them, report each

# Reconcile two tables and print a bridge that closes to zero
python ground-truth-analysis/scripts/reconcile.py --truth ledger.csv \
    --candidate export.xlsx --key order_id --value amount

# Keep the suite itself honest
python context_cost.py --detail      # what each level costs, per file
python validate.py                   # routing, budgets, frontmatter, fences
```

`reconcile.py` is stdlib-only and uses exact decimal arithmetic, so a float
artefact never gets reported as a finding; it decomposes the total gap into
missing rows, extra rows, and value differences that sum back to it exactly.
`run_repo_checks.sh` never invents commands — it reads the Makefile,
`package.json` scripts, `pyproject.toml`, `go.mod`, and `Cargo.toml`, so what
passes locally is what CI runs. `validate.py` exits non-zero on a broken route,
an unreachable file, an over-budget core, a name mismatch, or an unbalanced code
fence; run it after editing any skill.

## Installing

These are project skills: cloning this repository makes them available in
sessions started here. To use them everywhere, copy or symlink them into your
personal skills directory:

```bash
cp -r .claude/skills/* ~/.claude/skills/            # copy

for d in .claude/skills/*/; do                      # or symlink, so edits propagate
  [ -f "$d/SKILL.md" ] && ln -sfn "$(pwd)/${d%/}" ~/.claude/skills/
done
```

Claude loads a skill automatically when the work matches its description, or you
can invoke one directly: `/repo-architect`, `/python-engineering`, and so on.

## Structure

```
<skill>/
├── SKILL.md          standing rules + a routing table — loads on trigger
├── references/       task-shaped depth, loaded only when routed to
├── assets/           templates to fill in (docs-craft, ground-truth-analysis)
└── scripts/          executable, deterministic work
```

Every `SKILL.md` has the same shape, and the split between levels is deliberate:

- **The core** holds only what applies to *every* task in that domain — the
  standing rules and the done-check. It stays in context for the whole session
  once loaded, so it has to be the highest-value tokens available.
- **The routing table** names a condition and a file: *"if you are designing
  types, generics, or protocols → `references/typing-and-data.md`"*. Conditions
  are task-shaped rather than topic-shaped, so the decision to read is cheap.
- **The references** are read at the moment the question comes up, never
  speculatively. Every one opens by stating when to read it, so a wrong turn is
  caught in the first two lines.

**References stay flat — one file per topic, no per-language subdirectories.**
A reference that covers several languages (`languages.md`, `layouts.md`,
`frameworks.md`, `profilers.md`) keeps them as sections under a table of
contents, and the routing table says to read only the section that applies.
Fanning these out into a file per language costs less per read but multiplies
the surface a reader has to hold, and it makes the suite look like it has a
skill per language when it deliberately does not.

## Context cost

Three levels, each paid for only when it earns its place:

| Level | What | Cost |
|---|---|---|
| 1 — always | Nine descriptions in the skill listing | ~1,300 tokens total |
| 2 — on trigger | One `SKILL.md` core | ~900–1,500 tokens |
| 3 — on demand | One reference, routed to by task | ~200–3,900 tokens |

A session that orients, writes, and ships costs roughly 5–6k tokens of skill
context. Carrying all nine skills in full would cost ~76k. Run
`python context_cost.py` for the current numbers; it fails if a core has grown
past budget.

For perspective on where tokens actually go: a single unnecessary read of a
2,000-line source file costs ~25,000 tokens — more than every core in this suite
combined. That is why `codebase-recon` exists, and why it is the highest-leverage
skill here.

**If you want level 1 smaller still**, set `disable-model-invocation: true` on
the skills you would rather trigger by hand. Their descriptions leave the
always-in-context listing entirely, and `/skill-name` still loads them in full.
Good candidates are the ones you reach for deliberately rather than
mid-task — `perf-engineering`, `docs-craft`.

There is also a [`paths`](https://code.claude.com/docs/en/skills) frontmatter
glob that limits auto-loading to matching files. It is left off here on purpose:
`paths: ["**/*.py"]` on `python-engineering` would stop it loading for "write me
a Python script" before any `.py` file exists, which is exactly when it is most
useful.

## What these are opinionated about

- The reader of your code is a stranger under time pressure. Everything else
  follows from that.
- Reading is the expensive operation, in tokens and in attention. Search first,
  read narrowly, and stop when you can name the file, the function, and the test.
- Structure is decided before the first file, and restructuring later is normal
  work — done as mechanical, verifiable steps.
- Check what is current before choosing a stack. Version numbers, EOL dates, and
  which library is maintained all move faster than any model's training data.
- Performance is measured, never guessed, and every optimisation carries the
  number that justified it. The ceiling, though, is set at design time.
- A test earns its place by failing when behaviour breaks, and only then.
- A number that differs is a symptom; the finding is the mechanism that produced
  it, sized so the explained causes sum exactly to the gap.
- Documentation ships in the same commit as the code, or it rots.
- "It runs" is not "it is done", and the report at the end says what was
  verified and what was skipped.
