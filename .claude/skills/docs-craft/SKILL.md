---
name: docs-craft
description: Write the documentation a repository actually needs so a newcomer can run it, extend it, and understand why it is built this way — README, CONTRIBUTING, CHANGELOG, API/docstring reference, architecture decision records, and docs/ organised by the four Diataxis modes. Use this when creating or improving any documentation: "write a README", "document this", "add docstrings", "the docs are out of date", "explain how this works", "write a changelog", "record this decision", or as the finishing step of any project or feature that someone else will use. Also use when setting up a new repository, since the README and .env.example are part of the first commit.
---

# Documentation craft

Documentation is not the thing you do after the work; it is part of the work.
Code that nobody can run, extend, or reason about is not finished, however good
it is inside.

The test is concrete: **a competent stranger, given only this repository, should
be able to run it, make a small change, and know whether their change is
correct** — without asking anyone. Everything below serves that.

Two failure modes to design against. **Missing docs** cost every newcomer the
same day of confusion, repeatedly, forever. **Wrong docs** are worse: they are
trusted, and they send people down paths that no longer exist. So write less
documentation than you feel you should, put it where it will be maintained, and
make as much of it as possible verifiable by machine.

## What a repository owes its reader

| File | Answers | When it is required |
|---|---|---|
| `README.md` | What is this, how do I run it, how do I test it | Always, from the first commit |
| `.env.example` | What configuration exists and what each value is | As soon as config exists |
| `CONTRIBUTING.md` | How do I set up, test, and submit a change | Once more than one person touches it |
| `LICENSE` | May I legally use this | Always — absent means nobody may |
| `CHANGELOG.md` | What changed, and does it break me | Anything versioned or released |
| `docs/adr/` | Why is it built this way | When a decision is expensive to reverse |
| `docs/` | Everything longer than the README | When the README exceeds one screen of prose |
| Docstrings / doc comments | What does this function do, exactly | On every public API |

Write these as you go. Documentation written at the end is written from memory,
by someone who has lost the newcomer's perspective and no longer remembers which
parts were confusing.

## The README

The README is read by someone deciding, in about ten seconds, whether this
repository is relevant to them — and then, if it is, trying to run it. Optimise
the first screen for exactly that.

**Required, in this order:**

1. **Name and one sentence** saying what it does and for whom. Not "a project
   for managing things" — "a CLI that syncs Postgres tables into BigQuery on a
   schedule."
2. **Status badges** if CI exists — build, coverage, version. They answer "is
   this alive" instantly.
3. **Quick start**: the shortest path from clone to running, as commands that
   can be copy-pasted and that actually work in that order. This is the single
   most valuable section in the file.
4. **Requirements**: language version, and every service (database, queue,
   credentials) needed. Discovering the fourth prerequisite by hitting an error
   is the most common newcomer experience, and it is entirely avoidable.
5. **Configuration**: a table of every environment variable — name, required,
   default, description — kept in sync with `.env.example`.
6. **How to run the tests.** One command. Its absence is why contributors submit
   untested changes.
7. **Project layout**: one line per top-level directory, so a reader can
   navigate without opening files.
8. **License**, and where to get help.

Then stop. Deep usage, architecture, and tutorials belong in `docs/`, linked
from here. A README that scrolls for ten screens is one nobody reads to the end
of.

**The rules that keep a README true:**

- **Every command must actually run**, in the order given, from a clean clone.
  Run them. A README whose first command fails destroys trust in the rest of the
  file.
- Write for someone who has never used the project: no internal jargon, no
  team-specific acronyms, no "just" (it is never just).
- Show real commands with real values, not `<PLACEHOLDER>` where a working
  example is possible.
- If setup genuinely takes more than a handful of steps, that is a signal to
  fix the setup — a script, a Makefile, a devcontainer — not to write longer
  instructions.

`assets/README-template.md` is a fill-in skeleton with the sections in order.

## Organising `docs/`: four kinds, never mixed

The Diátaxis framework observes that documentation serves four distinct needs,
and that most bad documentation is two of them fused into one document that
serves neither. Split by *what the reader is doing*:

| Kind | Reader's situation | Written as | Example |
|---|---|---|---|
| **Tutorial** | Learning; no context yet | A lesson you guarantee works end to end | "Build your first pipeline" |
| **How-to** | Has a specific goal, already competent | A recipe, assumes background | "How to add a new data source" |
| **Reference** | Needs a precise fact, fast | Dry, complete, structured, scannable | API and CLI reference |
| **Explanation** | Wants to understand *why* | Discursive prose, discusses alternatives | "Why we chose event sourcing" |

The practical rules:

- **A tutorial must never explain trade-offs** — it must work, start to finish,
  with no decisions for the reader to make. A learner who has to choose is stuck.
- **Reference must never teach.** It is looked up, not read. Be complete and
  consistent; every entry has the same shape.
- **How-to guides assume competence.** They answer "how do I X", not "what is X".
- **Explanation is where the reasoning goes** — the alternatives you rejected,
  the constraints, the history. It is what stops the next person re-litigating a
  settled decision.

```
docs/
├── tutorials/       01-getting-started.md
├── how-to/          add-a-data-source.md, deploy-to-staging.md
├── reference/       api.md, cli.md, configuration.md
├── explanation/     architecture.md, why-event-sourcing.md
└── adr/             0001-use-postgres.md
```

More detail and the diagnostic for a document that is trying to be two things at
once is in `references/diataxis.md`.

## API documentation and docstrings

Document the public surface. Private helpers get a comment only when
non-obvious — documenting everything trains readers to skip all of it.

A doc comment states what the function does, what the parameters mean (including
units and valid ranges the type cannot express), what it returns, what it
raises, and any non-obvious behaviour: side effects, cost, thread-safety,
idempotency.

```py
def charge(order: Order, *, idempotency_key: str) -> Charge:
    """Charge the customer for an order.

    Args:
        order: Must be in PENDING state; charging any other state is an error.
        idempotency_key: Retries with the same key return the original charge
            rather than charging twice. Callers must reuse the key on retry.

    Returns:
        The completed Charge, including the gateway's transaction id.

    Raises:
        CardDeclined: The gateway rejected the card. Not retryable.
        GatewayUnavailable: Transient; safe to retry with the same key.
    """
```

Notice what the annotations could not say: the state precondition, the retry
contract, and which failure is retryable. **That is what a doc comment is for.**
Restating the type signature in prose adds nothing and rots.

Per-language conventions: Google or NumPy style docstrings (Python — pick one
and be consistent), TSDoc (`@param`, `@returns`, `@throws`), godoc (a complete
sentence starting with the identifier's name), rustdoc (`///`, with examples that
are compiled and run as tests), Javadoc/KDoc.

**Prefer documentation the toolchain checks.** Rust doc tests, Python doctests,
and compiled examples cannot silently go stale, because CI fails when they do.
That property is worth more than better prose.

## Architecture decision records

An ADR captures one decision that would be expensive to reverse, at the moment
it is made, with the reasoning intact. Six months later the code shows *what*
was decided; only the ADR shows *why*, and without it teams re-argue settled
questions and undo constraints they cannot see.

Write one when the choice is hard to reverse, affects multiple components, or
where a future reader would reasonably ask "why on earth is it done this way":
the database, the auth model, a language or framework, an API style, a
significant dependency, a deliberate deviation from convention.

Do not write one for a routine choice. Ten well-chosen ADRs beat a hundred.

```markdown
# 0007: Use Postgres for the event store

Status: Accepted            <!-- Proposed | Accepted | Deprecated | Superseded by 0012 -->
Date: 2026-08-18

## Context
What forces are at play: constraints, requirements, scale, team skills,
what we already run.

## Decision
What we are doing, stated actively: "We will store events in Postgres using
a single append-only table partitioned by month."

## Consequences
What becomes easier, what becomes harder, what we accept. Include the bad
parts honestly — an ADR that lists only benefits is not trusted.

## Alternatives considered
Each option, and the specific reason it was not chosen. This is the section
that stops the decision being re-litigated.
```

Numbered sequentially in `docs/adr/`, never edited after acceptance — a
superseded ADR gets `Status: Superseded by 0012` and stays, because the history
is the value. Template in `assets/adr-template.md`.

## CHANGELOG and versioning

A changelog is written for **users deciding whether to upgrade**, not for
developers reading history. `git log` already exists; a changelog is a curated,
human summary.

Follow Keep a Changelog: newest first, an `## [Unreleased]` section at the top,
and entries grouped under `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`,
`Security`. Write from the user's perspective — "the `--format` flag now accepts
`ndjson`", not "refactored the formatter module".

Semantic versioning (`MAJOR.MINOR.PATCH`): MAJOR for a breaking change to the
public API, MINOR for backward-compatible additions, PATCH for fixes. **Breaking
changes get their own prominent section with migration instructions** — that is
the single most valuable thing a changelog contains.

If commits follow Conventional Commits (see `ship-quality`), the changelog can
be generated, which is the version most likely to stay current.

## CONTRIBUTING

Needed as soon as a second person touches the repository. It answers: how do I
set up, how do I run tests and linters, what are the code conventions, how are
branches and commits named, what does a good pull request look like, and how
long until someone reviews it.

Keep it short and specific to *this* repository. Generic advice about being nice
adds length without reducing the number of questions.
`assets/CONTRIBUTING-template.md` is a starting point.

## Writing style

- **Second person, imperative, present tense**: "Run `make test`", not "the user
  should run" or "we will now run".
- **Front-load.** Put the answer in the first sentence; readers scan.
- **One idea per paragraph, short sentences.** Technical readers skim.
- **Show a real, complete example.** One runnable example teaches more than three
  paragraphs of description.
- **Say what will happen**, including how long it takes and what the output looks
  like, so a reader knows whether it worked.
- **Name the thing.** "The `--strict` flag" beats "the strictness option".
- Avoid "simply", "just", "obviously", "easy" — when it is not, the reader
  concludes the problem is them.
- Prefer a table for anything with more than three parallel items; prefer a
  diagram for anything with more than three interacting components.

## Keeping documentation true

Rotted documentation is a liability, so bias toward mechanisms over discipline:

- **Documentation lives in the repository**, in the same pull request as the
  change. Docs in a wiki drift within weeks because nothing forces them to move
  together.
- **Generate reference material from the source** (OpenAPI from route
  definitions, CLI help from the parser, API docs from docstrings). Handwritten
  reference is the first thing to go stale.
- **Make examples executable** — doctests, compiled examples, a CI step that runs
  the README's quick start. An example that CI runs cannot lie.
- **Delete documentation for things that no longer exist**, immediately. A stale
  page is worse than a missing one.
- Add a documentation line to the pull-request checklist: did the README, the
  configuration table, or the changelog need to change?

## References and assets

- `references/diataxis.md` — the four modes in depth, with the diagnostic for a
  document trying to be two things and how to split it.
- `assets/README-template.md` — fill-in README skeleton.
- `assets/adr-template.md` — architecture decision record template.
- `assets/CONTRIBUTING-template.md` — contributor guide skeleton.
