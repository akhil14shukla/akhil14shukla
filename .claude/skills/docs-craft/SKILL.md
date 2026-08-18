---
name: docs-craft
description: Write the documentation a repository actually needs so a newcomer can run it, extend it, and understand why it is built this way — README, CONTRIBUTING, CHANGELOG, docstrings and API reference, architecture decision records, and docs/ organised by Diataxis mode. Use when creating or improving any documentation: "write a README", "document this", "add docstrings", "the docs are out of date", "write a changelog", "record this decision", or as the finishing step of any project someone else will use. Also when setting up a new repository, since the README is part of the first commit.
---

# Documentation craft

Documentation is part of the work, not what follows it. Code nobody can run,
extend, or reason about is not finished, however good it is inside.

The test is concrete: **a competent stranger, given only this repository, should
be able to run it, make a small change, and know whether their change is
correct** — without asking anyone.

Design against two failure modes. **Missing docs** cost every newcomer the same
day of confusion, forever. **Wrong docs** are worse, because they are trusted.
So write less than you feel you should, put it where it will be maintained, and
make as much as possible verifiable by machine.

## What a repository owes its reader

| File | Answers | Required |
|---|---|---|
| `README.md` | What is this, how do I run it, how do I test it | Always, from the first commit |
| `.env.example` | What configuration exists, and what each value is | As soon as config exists |
| `LICENSE` | May I legally use this | Always — absent means nobody may |
| `CONTRIBUTING.md` | How do I set up, test, and submit a change | Once more than one person touches it |
| `CHANGELOG.md` | What changed, and does it break me | Anything versioned or released |
| `docs/adr/` | Why is it built this way | When a decision is expensive to reverse |
| Docstrings | What exactly does this do, and what can go wrong | On every public API |

Write these as you go. Documentation written at the end is written from memory,
by someone who has lost the newcomer's perspective.

## The standing rules

1. **The README's first screen answers what it is, how to run it, how to test
   it.** Everything longer moves to `docs/` and is linked. A README that scrolls
   for ten screens is one nobody finishes.
2. **Every command in the docs must actually run**, in the order given, from a
   clean clone. Run them. A README whose first command fails destroys trust in
   the whole file.
3. **Never mix the four documentation modes.** A tutorial that pauses to discuss
   trade-offs loses the beginner; a reference page that tells a story cannot be
   scanned. Split by what the reader is doing: learning (tutorial), doing
   (how-to), looking up (reference), understanding (explanation).
4. **Document what the type signature cannot say** — preconditions, units,
   retry contracts, which errors are retryable, side effects, thread safety.
   Restating the signature in prose adds nothing and rots.
5. **Second person, imperative, present tense.** "Run `make test`", not "the user
   should run". Front-load the answer; readers scan. Avoid "simply", "just",
   "obviously" — when it is not, the reader concludes the problem is them.
6. **Show one real, complete, runnable example.** It teaches more than three
   paragraphs of description.
7. **Documentation lives in the repository and ships in the same commit as the
   change.** Docs in a wiki drift within weeks because nothing forces them to
   move together.
8. **Prefer documentation the toolchain checks** — generated API reference, doc
   tests, compiled examples, a CI step running the README's quick start. An
   example CI runs cannot lie, and that property is worth more than better prose.
9. **Delete documentation for things that no longer exist**, immediately. A stale
   page is worse than a missing one.

## Read the reference or template that matches your task

| If you are… | Read |
|---|---|
| Writing or fixing a README, or documenting a public API with docstrings | `references/readme-and-reference.md` |
| Organising `docs/`, or unsure which kind of document you are writing | `references/diataxis.md` |
| Recording a decision, writing a release entry, or onboarding contributors | `references/adr-changelog-contributing.md` |

Fill-in templates: `assets/README-template.md`, `assets/adr-template.md`,
`assets/CONTRIBUTING-template.md`.
