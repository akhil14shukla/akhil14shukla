---
name: ship-quality
description: Turn working code into finished work — self-review the diff like a stranger, run the repository's own lint/typecheck/test gates, sweep for security and resource leaks, write atomic Conventional Commits and a pull request description that can be reviewed, and report honestly what was done and what was skipped. Use this at the end of ANY coding task, before committing, before opening a pull request, and whenever asked "is this ready", "review my changes", "commit this", "clean this up before merging", or "check this before I push". Also use when a task is finished and you are about to tell the user it is done.
---

# Shipping quality

"It runs" is the beginning of finishing, not the end. The gap between working
code and finished work is where most of the defects that reach production live —
not in the logic, but in the error path nobody looked at, the secret left in a
log line, the test that was never run, and the commit message that made a
bisect useless a year later.

This is a short, ordered gate. Work through it before you say anything is done.

## 1. Read your own diff as a stranger

Look at the actual diff, not your memory of what you wrote. `git diff` and
`git diff --staged`, file by file. You are looking for the things that are
invisible while writing and obvious while reading.

```bash
git diff                      # unstaged
git diff --staged             # staged
git status                    # anything accidentally added, anything forgotten
git diff --stat               # is the change the size you think it is?
```

Ask, in this order — design first, because a design problem is not fixable by
polishing:

- **Does this change belong here?** Right layer, right module, consistent with
  how the codebase already does this?
- **Does it do what was asked, all of it?** Re-read the original request. It is
  common to solve 80% and to have stopped noticing the other 20%.
- **Is there anything in the diff I did not mean to include?** Debug prints,
  commented-out code, a stray file, a formatting change to an unrelated file, a
  version bump you did not intend, a `.env`.
- **What happens on the unhappy path?** Empty input, missing key, zero, a
  negative number, a value ten times bigger than expected, the dependency being
  down, the same request arriving twice.
- **Does every error path either handle the failure or propagate it with
  context?** No silent `catch {}`, no ignored return value without a stated
  reason.
- **Does anything leak on the error path** — a file handle, a connection, a
  transaction, a lock?
- **Would a stranger understand why this code exists** from the names and the
  comments?

Fix what you find *before* running the tests, not after — the tests will not
tell you about any of it.

## 2. Run the repository's own gates

Do not invent commands. Find what this repository actually uses and run exactly
that, so that what passes locally passes in CI.

```bash
scripts/run_repo_checks.sh          # bundled with this skill: detects and runs them
```

The script inspects the repo (`Makefile`, `package.json` scripts, `pyproject.toml`,
`go.mod`, `Cargo.toml`, `.pre-commit-config.yaml`, CI workflows) and runs the
format, lint, typecheck, and test commands it finds, reporting each. Run it from
the repository root; `--list` shows what it would run without running it.

If it finds nothing, read `.github/workflows/*.yml` — whatever CI runs is the
definition of "passing", and matching it locally is the whole point.

**Every gate must actually pass.** Specifically:

- A test you did not run is a test you cannot claim passes.
- Never skip, `xfail`, delete, or weaken a failing test to reach green without
  saying so explicitly in your report. That converts a visible problem into a
  hidden one, and it is the single most damaging thing you can do here.
- A lint rule you disabled with an inline suppression needs a comment saying
  why. A blanket `# noqa` or `eslint-disable` on a whole file is not acceptable.
- If a check fails for a reason that predates your change, verify that claim
  (`git stash` and run it again) and say so rather than assuming.

## 3. Security and safety sweep

Most of these take seconds to check and are expensive to miss.

- **Secrets**: no keys, tokens, passwords, connection strings, or private keys
  in the diff — including in tests, fixtures, comments, and example config.
  `git diff | grep -Ei "api[_-]?key|secret|password|token|BEGIN .*PRIVATE KEY"`
  is a cheap first pass. If a secret was ever committed, it must be **rotated**,
  not just removed — the history keeps it.
- **Injection**: parameterised SQL only, never string-built queries. No shell
  command built from user input (`shell=True`, string concatenation into
  `exec`). No `eval` of anything that came from outside.
- **Input validation at the boundary**: every external input — request bodies,
  query params, file uploads, webhook payloads, environment — is validated
  before use, with size limits.
- **Authorisation on every path**: not just the UI, and not just the happy path.
  Check that the *object* belongs to the requesting user, not merely that the
  user is logged in — the most common real vulnerability is a missing ownership
  check on an id from the URL.
- **Output**: no personal data, tokens, or full payloads in logs or error
  messages returned to callers. Escape anything rendered into HTML.
- **Dependencies**: if you added one, is it maintained, popular enough to be
  scrutinised, appropriately licensed, and pinned in the lockfile?
- **Resource limits**: pagination on anything that can grow, timeouts on every
  network call, bounded concurrency, bounded caches, a size limit on uploads.

## 4. Documentation that must move with the code

Check each and update if the change touched it — this is where documentation rot
begins, and it costs a minute now versus a stranger's afternoon later:

- README: quick start, configuration table, project layout still true?
- `.env.example`: does it list every variable the code now reads?
- Doc comments on anything whose signature or contract changed.
- CHANGELOG: an entry under `## [Unreleased]`, written from the user's
  perspective.
- An ADR if you made a decision that is expensive to reverse (see `docs-craft`).

## 5. Commit

**One logical change per commit.** A commit that adds a feature, reformats two
files, and renames a variable cannot be reviewed, reverted, or bisected. Split
it: `git add -p` stages by hunk.

Refactors and behaviour changes go in **separate commits** — that is what lets a
reviewer trust "no behaviour change" without reading every moved line.

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<optional scope>): <imperative summary, ~50 chars, no full stop>

Why this change was needed, and anything a reader would otherwise have to
reconstruct: the constraint that forced this approach, the alternative that
did not work, the measurement that justified an optimisation. Wrap at 72.

Refs: #412
```

Types: `feat` (new capability, MINOR), `fix` (bug, PATCH), `refactor`, `perf`,
`test`, `docs`, `build`, `ci`, `chore`. A breaking change is `feat!:` or a
`BREAKING CHANGE:` footer, and it must describe the migration.

**The subject says what, the body says why.** The diff already shows what
changed; it can never show why. A year later during a bisect, "why" is the only
thing anyone needs.

```
fix(auth): reject tokens issued before a password change

Tokens stayed valid after a password reset, so a stolen token survived the
one action a user takes to revoke it. We now compare the token's issued-at
against the user's password_changed_at.

This invalidates all existing sessions on deploy, which is intended.

Refs: SEC-88
```

Before committing, check the branch. If you are on the default branch, create a
feature branch first. Never commit `.env`, credentials, build output, or
dependency directories — if `git status` shows something surprising, stop and
look at it rather than `git add -A`.

## 6. Pull request description

Reviewers give a real review to a small pull request and a rubber stamp to a
large one. Under ~400 changed lines is the target; if yours is larger, consider
whether it splits.

```markdown
## What
One or two sentences. The change, not the implementation tour.

## Why
The problem this solves, with a link to the issue.

## How
Only the decisions a reviewer could not infer from the diff: why this approach,
what alternative was rejected, anything deliberately out of scope.

## Verification
How you know it works: tests added, what you ran manually, before/after numbers
for a performance change, screenshots for anything visual.

## Risk
What could break, what to watch after deploy, how to roll back. Migrations,
breaking changes, and anything requiring a config change in another system.
```

If the repository has a pull request template, use its headings instead.

Point out your own uncertainties in the description. A reviewer who is told
"I was unsure whether the retry should be idempotent here" reviews that spot
carefully; one who is not, does not.

## 7. Report honestly

The last step, and the one most often done badly. Tell the user:

- **What you did**, in a couple of sentences.
- **What you verified, and how** — which commands you actually ran and what they
  said. "Tests pass" is only claimable if you ran them.
- **What you did not do**: scope you deliberately left, a test you could not
  write, a check that could not run in this environment, an assumption you made
  where the requirement was ambiguous.
- **What you are unsure about**, specifically.

If something failed, say so plainly with the output, rather than reporting
success with a caveat buried at the end. A partially-finished task reported
accurately is useful work; a finished-sounding report that does not survive
contact with CI costs far more than it saved.

## The gate, condensed

```
[ ] Read the whole diff; nothing unintended in it
[ ] The original request is fully satisfied, or the gap is stated
[ ] Edge and error paths considered; no silent failures; no leaked resources
[ ] format / lint / typecheck / tests all actually run and pass
[ ] No test skipped or weakened to get green (or it is stated loudly)
[ ] No secrets, no injection, authorisation checked on the object
[ ] README, .env.example, doc comments, CHANGELOG updated if affected
[ ] Commits atomic, Conventional, body explains why
[ ] PR description covers what / why / verification / risk
[ ] Report says what was verified and what was skipped
```

## References

- `references/commits-and-git.md` — Conventional Commits in full, splitting a
  messy working tree into clean commits, rebase vs merge, fixing a bad commit
  safely, and what makes a branch reviewable.
- `references/review-checklist.md` — a deeper per-category review checklist
  (correctness, concurrency, data, API compatibility, operations) for changes
  where the stakes justify it.
- `scripts/run_repo_checks.sh` — detects and runs this repository's own
  format/lint/typecheck/test commands.

Related: `code-craft` for the writing standard the review is against,
`testing-craft` for whether the tests are worth anything, and `docs-craft` for
the documentation set.
