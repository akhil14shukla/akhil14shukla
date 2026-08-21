# Turning a completed reconciliation into a reusable skill

Read this when a comparison will happen again — every month-end, every release,
every vendor file — or when you have been asked to capture "how we check this"
so someone else can run it. The output is a new skill whose whole subject is
*this* comparison, sitting alongside this one: `ground-truth-analysis` teaches
the method; the generated skill encodes the answers this particular comparison
has already paid for.

## Is it worth codifying?

Yes if two or more hold: the comparison recurs on a schedule; it has bitten
someone before; the correct contract (grain, scope, as-of, units) is
non-obvious; there are known recurring causes; or somebody other than you will
run it. No if it was a one-off investigation — write the report instead and move
on.

## Harvest the conversation before it scrolls away

An analysis conversation contains four kinds of durable knowledge and a lot of
noise. Pull out only these, quoting the run for evidence but keeping the *rule*:

1. **The contract that turned out to be correct**, including every assumption
   that had to be resolved and how. This is the most valuable part: it is what
   the next person will get wrong.
2. **The check sequence that mattered**, in the order that catches problems
   earliest — including the checks that found nothing but would have been
   expensive to skip, marked as such.
3. **The causes seen, with their signatures and tests** — a local version of
   `references/hypotheses.md` ranked by what actually happens in *this* feed.
   Include the false leads that were ruled out, and how, so nobody re-runs them.
4. **The mechanics** — file locations and naming, the query or script, the
   thresholds and where they came from, the report format, who receives it.

Leave out: the specific numbers from one run (they date the skill instantly),
the narrative of how the investigation went, and anything already covered by
this skill's method. A generated skill that restates "define the grain" without
saying *what the grain is here* has captured nothing.

## Shape of the generated skill

Same three levels as the rest of the suite:

```
<feed>-reconciliation/
├── SKILL.md         contract, run order, known causes, done check
├── references/      only if the core would exceed ~1,500 tokens
└── scripts/         the deterministic run, if there is one
```

Fill `assets/recon-skill-template.md` — it is the structure above with prompts
for each section. Rules for the fill:

- **The core is specifics, not method.** Every line should be something a
  competent analyst could not have guessed: the real grain, the real filter, the
  timezone, which side wins a disagreement, the actual tolerance and where the
  number came from.
- **Name the systems, files, and columns as they are actually called**, since
  that is what the next person will search for.
- **Known causes go in a table with signature and test**, ordered by how often
  each one is the answer here. Give each a typical size so a fresh reading can
  be sanity-checked against history.
- **Point back, do not restate.** One line: "method, adversarial checks, and
  report shape: `ground-truth-analysis`." That keeps the generated skill small
  and stops the two drifting apart.
- **If a step is deterministic, make it a script** rather than prose. Anything
  involving column mappings, thresholds, or a fixed sequence of joins belongs in
  code the skill invokes.

## Write the description for triggering

The description is the only part that is always in context, and the skill is
useless if it does not load at the right moment. Include the words a person
actually types: the file name (`vendor_payouts_*.csv`), the system names, the
metric name, the ritual ("month-end close"), and the symptom ("payouts don't
match the ledger"). Write it as *when to use*, not as a summary of contents.

## Prove it before you ship it

- Run the generated skill against the **most recent completed period** and check
  it reproduces the conclusion that was reached by hand.
- Run it against a period with a **known problem** and confirm it surfaces that
  problem — a check suite that has never caught anything is untested, not clean.
- Have someone who did not do the analysis follow it end to end without asking
  you a question. Every question they ask is a missing line in the skill.
- If it lives in this suite, run `python validate.py` from the skills directory:
  it checks frontmatter, routing, budgets, and that every bundled file is
  reachable.

## Keep it alive

Each time the comparison runs and something new appears, add the cause to the
table with its signature — that table is the compounding asset. When a cause is
fixed at source, keep the row and mark it fixed with a date; when it recurs,
that history is the fastest diagnosis available. Review the contract whenever
either system changes shape, and date the skill's last verification so a reader
can judge how much to trust it.
