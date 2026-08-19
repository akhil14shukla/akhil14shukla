---
name: ship-quality
description: Turn working code into finished work — self-review the diff like a stranger, run the repository's own lint/typecheck/test gates, sweep for security and leaks, write atomic Conventional Commits and a reviewable pull request, and report honestly what was done and skipped. Use at the end of ANY coding task, before committing, before opening a pull request, and when asked "is this ready", "review my changes", "commit this", or "check this before I push". Also use when a task is finished and you are about to tell the user it is done.
---

# Shipping quality

"It runs" is the beginning of finishing. The gap between working code and
finished work is where most defects that reach production live — not in the
logic, but in the error path nobody looked at, the secret left in a log line,
the test that was never run, and the commit message that made a bisect useless a
year later.

## The gate

Work through these in order. Design problems come first because polishing does
not fix them.

**1. Read your own diff as a stranger.** `git diff`, `git diff --staged`,
`git status` — the actual diff, not your memory of it. Does this change belong
here? Does it do *all* of what was asked (re-read the original request)? Is
anything in the diff you did not mean to include — debug prints, commented-out
code, a stray file, an unrelated reformat? What happens on the unhappy path? Is
every error either handled or propagated with context? Does anything leak on the
error path? Fix what you find *before* running the tests; the tests will not
tell you about any of it.

**2. Run the repository's own gates.** Do not invent commands — run exactly what
CI runs, so green here means green there:

```bash
scripts/run_repo_checks.sh --list    # show what it detected
scripts/run_repo_checks.sh           # run them, report each
```

It reads the Makefile, `package.json` scripts, `pyproject.toml`, `go.mod`, and
`Cargo.toml`. If it finds nothing, read `.github/workflows/*.yml` — whatever CI
runs is the definition of passing.

**Every gate must actually pass.** A test you did not run is a test you cannot
claim passes. **Never skip, `xfail`, delete, or weaken a failing test to reach
green without saying so explicitly** — that converts a visible problem into a
hidden one, and it is the most damaging thing you can do here. If a failure
predates your change, verify that claim (`git stash`, re-run) rather than
assuming it.

**3. Sweep for security.** No secrets in the diff — including tests, fixtures,
and comments. Parameterised queries only. Every external input validated at the
boundary. **Authorisation checked on the object, not just the session** — "is
this order *this user's* order", which is the most common real vulnerability.
Nothing sensitive in logs or returned errors. Read
`references/security-sweep.md` for the full pass whenever the change touches
input handling, auth, money, personal data, or a new dependency.

**4. Move the documentation with the code.** README quick start and
configuration table, `.env.example`, doc comments whose contract changed, a
CHANGELOG entry under `## [Unreleased]`, an ADR if the decision is expensive to
reverse.

**5. Commit atomically.** One logical change per commit — `git add -p` stages by
hunk. Refactors and behaviour changes go in *separate* commits, which is what
lets a reviewer trust "no behaviour change" without reading every moved line.
Use Conventional Commits: `<type>(<scope>): <imperative summary>`, types `feat`,
`fix`, `perf`, `refactor`, `test`, `docs`, `build`, `ci`, `chore`, with `!` or a
`BREAKING CHANGE:` footer for breaks. **The subject says what; the body says
why** — the diff already shows what, and can never show why. Check the branch
first; if you are on the default branch, create a feature branch.

**6. Report honestly.** Say what you did; what you verified *and how*, naming
the commands you actually ran; what you did **not** do — scope left, a test you
could not write, a check that could not run here, an assumption you made; and
what you are unsure about. If something failed, say so plainly with the output
rather than reporting success with a caveat buried at the end. A partially
finished task reported accurately is useful work; a finished-sounding report
that does not survive CI costs far more than it saved.

## The gate, condensed

```
[ ] Whole diff read; nothing unintended in it
[ ] Original request fully satisfied, or the gap is stated
[ ] Edge and error paths handled; no silent failures; no leaked resources
[ ] format / lint / typecheck / tests actually run and pass
[ ] No test skipped or weakened to get green (or it is stated loudly)
[ ] No secrets, no injection, authorisation checked on the object
[ ] README, .env.example, docstrings, CHANGELOG updated if affected
[ ] Commits atomic and Conventional; body explains why
[ ] Report says what was verified and what was skipped
```

## Read the reference that matches your task

| If you are… | Read |
|---|---|
| Splitting a messy tree into commits, writing a PR description, rebasing, or fixing a bad commit | `references/commits-and-git.md` |
| Touching input handling, auth, money, personal data, or adding a dependency | `references/security-sweep.md` |
| Reviewing a high-stakes change — migrations, API compatibility, concurrency, operations | `references/review-checklist.md` |

Adjacent skills: `code-craft` for the standard being reviewed against,
`testing-craft` for whether the tests are worth anything, `docs-craft` for the
documentation set.
