# Contributing to <project>

<!-- Keep this short and specific to THIS repository. Generic advice about being
     nice adds length without reducing the number of questions asked. -->

## Setting up

```bash
git clone <url> && cd <project>
<install dependencies>
cp .env.example .env
<verify the setup works — a command whose success proves the environment is good>
```

<!-- If setup is more than a handful of steps, fix the setup (a script, a
     Makefile, a devcontainer) rather than writing longer instructions. -->

## Running the checks

Everything CI runs, runnable locally in one command:

```bash
<format> && <lint> && <typecheck> && <test>
```

Please run this before opening a pull request — it is the same set CI runs, so
a green run locally means a green run there.

## Conventions

- **Code style** is enforced by <formatter>; do not hand-format. Run
  `<format command>` before committing.
- **Tests**: every behaviour change needs a test; every bug fix needs a
  regression test that fails before the fix.
- **Structure**: <one line on where new code goes — e.g. "one directory per
  domain under `src/`; shared code only if two domains use it">.
- **Documentation**: update the README's configuration table and the changelog
  in the same pull request as the change.

## Branches and commits

- Branch from `main`: `<type>/<short-description>` (e.g. `feat/bulk-export`).
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):
  `feat(orders): add bulk export`. The body explains *why*, not what.
- Keep commits atomic — one logical change each. Separate refactors from
  behaviour changes so reviewers can trust that a move is only a move.

## Pull requests

- Keep them small. Under ~400 changed lines gets a real review; a 2,000-line
  pull request gets a rubber stamp.
- The description says **what changed, why, and how you verified it**. Include
  screenshots for anything visual.
- Note anything you deliberately left out of scope.
- CI must be green. Do not skip or disable a failing test to get there — if a
  test is wrong, fix it and say so in the description.

## Review

<!-- Set the expectation, so contributors are not left wondering. -->

We aim to respond within <N> working days. Reviewers look at design first, then
correctness, then tests, then style. A comment prefixed `Nit:` is optional.

## Reporting bugs

Open an issue with: what you did, what you expected, what happened, and the
versions involved. A minimal reproduction is the single most useful thing you
can include.

## Security

Do not open a public issue for a security problem. Email <address> instead.
