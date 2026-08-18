---
name: codebase-recon
description: Find your way around an unfamiliar codebase and change the right thing, without burning context on files you did not need. Search before reading, read ranges not whole files, trace one real path, and stop when you can name the file, the function, and the test. Use BEFORE editing anything in a repository you have not already read in this session, and whenever asked "how does X work here", "where is Y handled", "add Z to this codebase", "why does this happen", or when a task starts with exploring code you did not write.
---

# Codebase recon

Reading is the expensive operation, and it is expensive in both currencies.
A 2,000-line file costs roughly 25,000 tokens to read; the search that would
have found the 40 lines you actually needed costs about 200. Ten unnecessary
file reads cost more than every skill in this suite combined.

It also costs *quality*. Someone who reads three files at random and starts
typing writes a plausible change that duplicates an existing helper, misses the
convention, and breaks something two directories away. Someone who spends four
cheap searches first writes the change that belongs there.

So the discipline below is not frugality for its own sake — **narrow, targeted
reading is also how you find out what the codebase already does.**

## The loop

1. **Map before you read.** The tree, the manifest, the README's layout section,
   the entry point. Two or three cheap commands orient everything that follows:
   ```bash
   git ls-files | head -50                 # what exists, honouring .gitignore
   git ls-files | sed 's|/[^/]*$||' | sort | uniq -c | sort -rn | head -20
   ```
   The second gives you file counts per directory — the biggest directories are
   where the system's weight actually is, which is rarely where the README
   suggests.

2. **Locate by concept, not by filename.** Grep for the *domain word*, the exact
   error string a user reported, the route path, the config key, the SQL table
   name. These are unique and lead straight to the code. Filenames lie; a user
   -visible string does not.

3. **Read narrowly.** `grep -n` to get line numbers, then read a range around
   them, not the file. Widen only when the narrow read genuinely fails to answer
   the question — and it usually does answer it.

4. **Trace exactly one real path end to end.** One request from route to handler
   to service to storage teaches you more about a system's shape than skimming
   ten files. You learn the conventions, the layering, and the error style in
   one pass, and they hold for the rest of the codebase.

5. **Read the tests to learn behaviour.** They state intent with real inputs and
   real expected outputs, and they are shorter than the implementation. When you
   want to know what a function is *supposed* to do, its test is the cheapest
   answer available.

6. **Stop when you can name the file, the function, and the test.** That is
   enough to make a change. Reading more is not diligence past that point; it is
   avoidance.

## The standing rules

- **Search before you read. Always.** A read without a preceding search is
  usually a guess wearing a costume.
- **Never read a whole file when you know the symbol.** `grep -n` then read the
  range. Reserve whole-file reads for files you are about to substantially
  rewrite, and for files under ~200 lines where the read is cheap anyway.
- **Batch independent searches into one turn.** Four greps issued together cost
  one round trip; four turns cost four.
- **Never re-read a file to verify your own edit.** The edit would have failed
  loudly if it had not applied. Re-reading to check is pure cost.
- **Filter command output at the source.** `| head`, `--stat`, `-l`, `-c`,
  `--oneline`. Say what you filtered so nobody thinks you saw the whole thing.
- **Prefer the cheap question.** `git log --oneline -5 -- path/` tells you who
  changed a file and why, faster than reading it. `git grep` searches history.
  A test name often answers a behaviour question outright.
- **If you are opening a fourth file to answer one question, stop.** You are
  lost, and more reading will not fix it — say what you have established, what
  you cannot find, and ask. That is cheaper for everyone than another ten files.
- **Write down what you learned** in your response, briefly: the entry point,
  the layer that owns the logic, the convention for errors and tests. It stops
  you re-deriving it later in the same session, and it is the context the user
  actually wants from you.

## Rough costs, for calibration

| Operation | Approx. tokens |
|---|---|
| `grep -rn "pattern" --include=*.py` (20 hits) | ~300 |
| `git ls-files` on a mid-size repo | ~500 |
| Reading a 200-line file | ~2,500 |
| Reading a 2,000-line file | ~25,000 |
| Reading a directory of ten such files | ~250,000 |

The lesson is not "never read" — it is that the *ordering* matters enormously.
Search narrows the target by an order of magnitude for a fiftieth of the cost.

Be deliberate rather than dogmatic: read a file in full when you are about to
rewrite it, when it is the one file the task concerns, when it is short, or when
a narrow read has already failed twice. Reading widely on purpose is fine;
drifting into it by default is what costs.

## Read the reference when you need it

| If you are… | Read |
|---|---|
| Navigating a specific ecosystem, or doing git archaeology to find why code exists | `references/navigating.md` |

Adjacent skills: `repo-architect` for what a good tree looks like once you can
see this one, `code-craft` for matching the conventions you just discovered.
