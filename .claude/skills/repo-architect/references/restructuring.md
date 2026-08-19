# Restructuring an existing codebase safely

Moving working code is a high-trust operation: if the build breaks, everyone
concludes the restructure was a mistake, even when the target tree was right.
The whole craft is in making the change reviewable and reversible at every step.

## Contents

- [The procedure in short](#the-procedure-in-short)
- [Decide whether it is worth it](#decide-whether-it-is-worth-it)
- [Step 1: inventory](#step-1-inventory)
- [Step 2: agree the target tree](#step-2-agree-the-target-tree)
- [Step 3: build the safety net](#step-3-build-the-safety-net)
- [Step 4: move in mechanical commits](#step-4-move-in-mechanical-commits)
- [Splitting a large module](#splitting-a-large-module)
- [Breaking an import cycle](#breaking-an-import-cycle)
- [Untangling a pile of scripts](#untangling-a-pile-of-scripts)
- [What not to do](#what-not-to-do)

## The procedure in short

The user asking for this usually has working code in a bad tree. Moving it is
worth doing — but a restructure that breaks the build destroys trust in the
whole idea, so do it as a sequence of boring, verifiable steps.

**Read `references/restructuring.md` before starting.** The short version:

1. **Inventory first.** List every file and what it actually does. Note the
   entry points and anything that is dead — deleting dead code before moving it
   is the cheapest win available.
2. **Write down the target tree and get agreement on it** before moving
   anything. Show it to the user as a tree diagram.
3. **Establish a safety net.** If there are no tests, add a few
   characterisation tests over the main paths first. Without them you are not
   restructuring, you are rewriting blind.
4. **Move mechanically, in small commits.** `git mv` (history is preserved and
   the diff shows a rename), one coherent group per commit, imports fixed, tests
   green after each. Never mix a move with a behaviour change — a reviewer must
   be able to trust that a move is only a move.
5. **Fix imports with the toolchain**, not by hand: your IDE's move-refactor,
   `ruff check --fix`, `gofmt -r`, `ts-morph`. Hand-editing imports across 80
   files is where the typos come from.
6. **Delete the compatibility shims** you left behind, in a final commit, once
   nothing references them.

Say clearly what you are doing and why: "these 30 scripts are one pipeline, so
I am grouping them into `src/pipeline/{ingest,transform,publish}` and adding a
single entry point; behaviour is unchanged and the tests prove it." A silent
large-scale move is unreviewable.

---

## Decide whether it is worth it

Restructure when the *shape* is blocking work:

- Adding a feature requires edits in five directories.
- Nobody can find where a behaviour lives without grepping.
- Import cycles are being worked around with function-level imports.
- One module is imported by everything and changed by everyone.
- Tests need most of the system booted, so nobody writes them.

Do **not** restructure because you prefer a different convention, because a
tutorial used a different tree, or as a side quest inside a feature PR. Churn
without a named problem burns review capacity and rewrites git blame for nothing.

State the problem in one sentence before you start: *"Every pricing change
touches four directories because the logic is split by layer, so I am grouping it
by domain."* If you cannot write that sentence, do not start.

## Step 1: inventory

Get the real picture before touching anything.

```bash
# Size and shape
find . -path ./.git -prune -o -name '*.py' -print | wc -l
tokei .            # or: cloc . — lines per language

# Biggest files: these are usually where the structural problem lives
find . -name '*.py' -not -path './.git/*' -exec wc -l {} + | sort -rn | head -20

# Who imports what (Python example; adapt the pattern per language)
grep -rn "^from \|^import " --include='*.py' src/ | sort | uniq -c | sort -rn | head -30

# Entry points
grep -rln "__main__\|def main(" --include='*.py' .

# Dead code candidates: defined but never referenced elsewhere
```

Write down, for each file: what it does, who calls it, and whether it is still
used. **Delete dead code before moving it** — it is the cheapest possible win,
and moving dead code makes the diff bigger for no benefit. Confirm with the user
before deleting anything you are unsure about.

## Step 2: agree the target tree

Show the user the before and after as trees, with a one-line rationale per
top-level directory, and get explicit agreement. This costs one message and
prevents a whole restructure being redone.

```
Now                          Proposed
src/                         src/
├── controllers/  (4 files)  ├── orders/     routes, service, repo, tests
├── services/     (4)        ├── payments/   routes, service, repo, tests
├── models/       (6)        ├── users/      routes, service, repo, tests
└── utils/        (11)       └── shared/     config, db, logging, errors

Why: a change to order pricing currently touches controllers/, services/,
models/ and utils/. After, it touches src/orders/ only.
utils/ splits: 6 files move into the domain that uses them, 3 become
shared/, 2 are unused and get deleted.
```

Name where every current file lands. "utils/ gets sorted out later" means it
never does.

## Step 3: build the safety net

You cannot verify a move without something that tells you behaviour is
unchanged. In order of preference:

1. **Existing tests.** Run them, note which pass. That is your baseline — write
   the numbers down.
2. **Characterisation tests** where coverage is thin. These do not assert what
   the code *should* do; they capture what it *currently* does, so any
   difference shows up. Ugly is fine — they are scaffolding.
   ```py
   def test_price_calculation_current_behaviour():
       # Not a specification — a snapshot of today's output, so the move is provably
       # behaviour-preserving. Replace with real assertions after the restructure.
       assert calculate_price(SAMPLE_ORDER) == 12750
   ```
3. **A smoke script** that exercises the main paths end to end, when the code is
   genuinely untestable as it stands.

If none of these is possible, say so explicitly to the user before proceeding
and let them decide whether the risk is acceptable. Do not restructure blind and
report success.

## Step 4: move in mechanical commits

The discipline is: **one kind of change per commit, tests green after each.**

```bash
git checkout -b restructure/domain-layout

# 1. Create the target directories (empty, with package markers).
mkdir -p src/orders && touch src/orders/__init__.py
git commit -m "refactor: add domain package directories"

# 2. Move ONE coherent group. git mv preserves history and shows a rename.
git mv src/controllers/order_controller.py src/orders/router.py
git mv src/services/order_service.py       src/orders/service.py
git mv src/models/order.py                 src/orders/models.py

# 3. Fix imports with tooling, not by hand.
ruff check --fix src tests          # or your IDE's move-refactor / ts-morph / gofmt -r

# 4. Prove it.
pytest
git commit -m "refactor: move order code into src/orders (no behaviour change)"

# Repeat per domain. Small commits mean a mistake costs one revert, not a day.
```

Rules that keep this reviewable:

- **Never mix a move with an edit.** If a moved file also needs a rename inside
  it, that is the next commit. A reviewer must be able to trust the message
  "no behaviour change" without reading every line.
- **Use `git mv`** (or move + `git add -A` so rename detection fires). A
  delete-plus-create loses history and produces an unreadable diff.
- **Run the full test suite after every commit**, not at the end. Bisecting one
  commit is easy; bisecting a 400-file move is not.
- **Keep a temporary shim** if external code imports the old path, and remove it
  in a final commit:
  ```py
  # src/services/order_service.py
  """Deprecated: moved to myapp.orders.service. Remove after v2.3."""
  from myapp.orders.service import *  # noqa: F401,F403
  ```
- **Update the imports in tests, docs, CI config, Dockerfiles, and entry-point
  declarations too.** Grep for the old path across the whole repo, not just
  source — `pyproject.toml` scripts, `package.json` bin, and CI workflows all
  reference paths.

## Splitting a large module

A 2,000-line file is split along the seams that already exist inside it, not
arbitrarily.

1. List the top-level definitions and group them by what they touch. Things that
   share state or call each other belong together.
2. Identify the group with the **fewest inbound dependencies** — extract that
   first, since nothing else needs changing to accommodate it.
3. Move it to a new module, import it back into the original, run tests.
4. Repeat. The original file shrinks toward whatever is genuinely cohesive.
5. When only re-exports remain, either delete the file or keep it as the
   package's public surface — that is a legitimate final state.

If a group cannot be extracted because everything references everything, that is
the real finding: the module has no internal structure, and it needs an interface
introduced (step: define the types the two halves exchange, then split along
that line).

## Breaking an import cycle

`a` imports `b`, `b` imports `a`. Moving the import inside a function makes the
error go away and the design problem stay. The three real fixes:

- **Extract the shared thing downward.** Usually both modules need one type or
  constant. Move it to `c`, have both import `c`. This resolves most cycles.
- **Invert the dependency.** If `a` is higher-level, `b` should not know about
  it: define an interface/protocol in `b` (or in a shared module), have `a`
  implement it, and pass the implementation in at composition time.
- **Merge them.** If two modules genuinely cannot be separated, they are one
  module pretending to be two.

## Untangling a pile of scripts

The common real-world case: 30 loosely related `.py`/`.sh` files at the root,
half of them copies of each other.

1. **Group by what they do**, not by name. Read them; names lie.
2. **Find the duplication.** Three scripts that each connect to the database and
   parse a CSV differently have one function hiding in them.
3. **Establish a single entry point** — a CLI with subcommands — so there is one
   documented way to run things.
4. **Move shared logic into `src/<project>/`** and make the scripts thin callers.
5. **Keep the old script names as one-line wrappers** for a release if anything
   (cron, CI, a colleague's muscle memory) invokes them by path, then delete.
6. **Write down what each command does** in the README as you go. Half the value
   of this exercise is that afterwards someone can find out what exists.

## What not to do

- Do not restructure and change behaviour in the same commit or PR.
- Do not rename files "while you are in there" — every rename is a merge
  conflict for someone else's open branch.
- Do not leave the repo half-moved across a long-lived branch. Land the moves in
  small pieces on the main branch, frequently, so nobody rebases across a
  1,000-file rename.
- Do not restructure with uncommitted work in the tree; start clean.
- Do not silently drop a file because you could not tell what it did. Ask.
