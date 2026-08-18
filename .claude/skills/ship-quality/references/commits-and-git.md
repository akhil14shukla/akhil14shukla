# Commits, branches, and git hygiene

Git history is documentation that cannot rot, because it is attached to the
change itself. A year from now, someone bisecting a regression will read your
commit message and it will be the only explanation that exists.

## Contents
- [Conventional Commits in full](#conventional-commits-in-full)
- [Writing the body](#writing-the-body)
- [Splitting a messy working tree](#splitting-a-messy-working-tree)
- [Fixing commits before they are pushed](#fixing-commits-before-they-are-pushed)
- [Rebase or merge](#rebase-or-merge)
- [Branches](#branches)
- [Things never to commit](#things-never-to-commit)

## Conventional Commits in full

```
<type>[(<scope>)][!]: <description>

[optional body]

[optional footer(s)]
```

- **type** — a noun, lowercase, required.
- **scope** — optional, in parentheses, naming the area: `fix(parser):`.
- **`!`** — marks a breaking change: `feat(api)!: require an auth header`.
- **description** — imperative mood ("add", not "added"), no trailing full stop,
  around 50 characters. It completes the sentence "if applied, this commit
  will…".

| Type | Use for | Version impact |
|---|---|---|
| `feat` | a new capability visible to users | MINOR |
| `fix` | a bug fix | PATCH |
| `perf` | a change made for performance | PATCH |
| `refactor` | restructuring with no behaviour change | none |
| `test` | adding or fixing tests only | none |
| `docs` | documentation only | none |
| `build` | build system, dependencies, packaging | none |
| `ci` | CI configuration | none |
| `chore` | maintenance with no src/test change | none |
| `style` | formatting only, no code meaning changed | none |

Breaking changes are either `!` after the type/scope, or a footer:

```
BREAKING CHANGE: `parse()` now returns a Result instead of throwing.
Callers must handle the error case; see MIGRATION.md.
```

Footers use git trailer format: `Refs: #412`, `Reviewed-by: …`,
`Co-authored-by: …`.

## Writing the body

The subject says *what*. The body says *why* — the only thing the diff can never
show. Include the body whenever the reason is not self-evident, which is most
of the time.

Answer as many of these as apply, in a sentence each:

- What was wrong or missing, and how did it show up?
- Why this approach rather than the obvious alternative?
- What did you measure, if this is a performance change?
- What does this deliberately not do?
- What should a future reader be careful about?

```
perf(reports): batch the per-order customer lookup

Generating the monthly report issued one customer query per order, so a
10k-order month made 10,001 round trips and took 94s.

Now fetched in one query keyed by customer_id and joined in memory:
94s -> 3.2s on the production-sized fixture. Memory rises by ~40MB for a
10k-order month, which is well inside the job's limit.

Refs: #1180
```

What not to write: "fix bug", "update code", "changes", "wip", "address review
comments" (say which comment and what changed), or a body that restates the diff
line by line.

## Splitting a messy working tree

You have five unrelated changes in one working tree. Do not commit them
together — a mixed commit cannot be reverted, reviewed, or bisected.

```bash
git add -p                    # stage hunk by hunk: y/n/s to split, e to edit
git commit -m "fix(auth): reject tokens issued before a password change"

git add -p                    # the next logical change
git commit -m "refactor(auth): extract token claims parsing"

git stash                     # park what is left while you verify
<run the tests>
git stash pop
```

If two changes are tangled in the same hunk, `e` lets you edit the staged hunk
by hand. If they are tangled in the same *line*, commit them together and say so
in the body.

**Verify each commit stands alone**: after staging, `git stash --keep-index`
leaves only the staged change in the tree, so you can run the tests against
exactly what you are about to commit.

## Fixing commits before they are pushed

Anything not yet pushed is freely rewritable, and a clean history is worth the
two commands.

```bash
git commit --amend                          # fix the most recent message or add a file
git rebase -i HEAD~4                        # reorder, squash, reword, drop
git commit --fixup <sha> && git rebase -i --autosquash HEAD~5
git reset --soft HEAD~1                     # undo the commit, keep the changes staged
```

**Once pushed to a shared branch, do not rewrite** unless you are certain nobody
has pulled it — a force push discards other people's work silently. On your own
unshared feature branch, `--force-with-lease` (never bare `--force`) refuses to
overwrite work you have not seen.

To undo a commit that is already public, `git revert <sha>` — it adds a new
commit, which is safe and honest.

## Rebase or merge

Both are fine; consistency within a repository matters more than the choice.

- **Rebase your feature branch onto the base branch** to keep history linear and
  make your changes easy to read as a sequence. Do this while the branch is
  yours alone.
- **Merge the base branch into yours** when the branch is shared, or when a
  conflict-heavy rebase would rewrite many commits.
- When resolving conflicts, regenerate lockfiles and generated files rather than
  hand-merging them — a hand-merged lockfile is usually wrong in a way that only
  shows up in CI.
- After any conflict resolution, run the full test suite. A resolution that
  compiles is not a resolution that works.

## Branches

- Name for the change: `feat/bulk-export`, `fix/token-expiry`,
  `refactor/order-module`. Not `patch-1`, not your name, not the ticket number
  alone.
- Branch from an up-to-date base, and keep the branch short-lived. A branch open
  for three weeks is a merge conflict accumulating interest.
- One concern per branch. "While I was in there" changes belong on their own
  branch — they are what turns a ten-minute review into an hour.

## Things never to commit

`.env` and any real credential; API keys, tokens, private keys, certificates;
`node_modules/`, `venv/`, `target/`, `dist/`, `build/`; `.DS_Store` and IDE
directories; large binaries and datasets (use Git LFS or object storage);
generated files that a build step produces; and anything containing personal
data.

Add these to `.gitignore` at the start of a project — a `.gitignore` written
after the fact does not remove what is already tracked.

**If a secret was ever committed, it is compromised.** Removing it in a later
commit does not remove it from history. Rotate the credential, then optionally
purge the history (`git filter-repo`) — in that order, because rotation is what
actually protects you.
