# ADRs, changelogs, and contributor guides

Read this when recording a decision, writing a release entry, onboarding
contributors, or setting up the mechanisms that stop documentation rotting.

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
