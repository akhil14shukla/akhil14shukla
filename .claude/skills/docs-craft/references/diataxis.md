# The four documentation modes, in depth

Read this when organising `docs/`, or when you cannot tell which kind of
document you are writing and it is coming out as two things at once.

Most unsatisfying documentation is two of these fused into one document. The
tutorial that stops to discuss trade-offs loses the beginner; the reference page
that tells a story cannot be scanned. Splitting by the reader's *situation* is
what fixes it.

Two axes place the four modes:

|  | **Practical** (doing) | **Theoretical** (thinking) |
|---|---|---|
| **Serving study** (learning) | Tutorial | Explanation |
| **Serving work** (a task at hand) | How-to guide | Reference |

## Choosing the mode

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

---

## Tutorial — learning-oriented

The reader has no context and needs a first success. Your job is to get them
there, not to teach them everything.

**Rules:**
- It must work, exactly as written, every time. Test it on a clean machine —
  a tutorial that fails at step 4 is worse than none, because the reader
  concludes the whole project is broken.
- **No choices.** Every decision is made for the reader. "You could use X or Y"
  strands a beginner who has no basis to choose.
- **No explanation of alternatives or trade-offs.** Link to an explanation page
  for readers who want it; do not interrupt the lesson.
- Concrete and minimal: one narrow path to one visible result.
- **Show what success looks like** at each step — the output, the file that
  appears, the page that renders. That is how the reader knows to continue.
- Say how long it takes and what they will have at the end, up front.

**Smells**: "depending on your setup"; a paragraph beginning "it is worth
understanding why"; a step that fails for some readers; more than about fifteen
steps.

## How-to guide — task-oriented

The reader knows the domain and has a specific goal. They arrived from a search
for "how do I X".

**Rules:**
- **Title as the goal**: "How to add a new data source", not "Data sources".
  This is what makes it findable.
- Assume competence. Do not re-explain what the reader already knows to have
  asked the question.
- **A series of steps that solve one real problem.** Not a feature tour.
- It is fine to note where the reader must adapt something to their situation —
  unlike a tutorial, they have the judgement to do so.
- Link to reference for detail; do not inline the whole option list.

**Smells**: it begins by explaining what the feature is; it covers three loosely
related tasks; it is really a tutorial with the safety removed.

## Reference — information-oriented

The reader needs one precise fact quickly and is not reading top to bottom.

**Rules:**
- **Structure mirrors the code's structure**, so a reader can predict where a
  thing is documented.
- **Consistent and complete.** Every entry has the same shape — signature,
  parameters, return, errors, example. Inconsistency is what makes reference
  unusable.
- **Dry and factual.** No opinions, no teaching, no narrative.
- **Generate it from the source** wherever possible. Handwritten reference is the
  first documentation to go stale, and stale reference is actively harmful
  because it is trusted.
- Include units, ranges, defaults, and constraints the type signature cannot
  express.

**Smells**: prose paragraphs; "you probably want to"; entries with different
shapes; anything that had to be updated by hand when the code changed.

## Explanation — understanding-oriented

The reader wants to understand the shape of the thing: why it is built this way,
what the alternatives were, what the constraints are. Often read away from the
keyboard.

**Rules:**
- **Discuss alternatives and admit trade-offs.** This is the one mode where
  opinion and history belong.
- Provide context: what problem this design solves, what it deliberately does
  not.
- Make connections between parts; this is where a system-level mental model gets
  built.
- **No instructions.** If the reader must do something, that is a how-to.

**Smells**: numbered steps; a command to run; being the only place a required
fact is documented.

## Diagnosing a mixed document

Read a page and ask what the reader is doing. If the answer changes partway
through, split it.

Common fusions and their fixes:

- **Tutorial + explanation** — the most common. The lesson keeps pausing to
  justify itself. *Fix*: move the reasoning to an explanation page and link to it
  once at the end: "Curious why we used a queue here? See Architecture."
- **How-to + reference** — the guide inlines every flag. *Fix*: use the two or
  three flags the task needs, link to the reference for the rest.
- **Reference + explanation** — a parameter description that argues for a
  particular usage. *Fix*: state the fact; move the argument.
- **Everything in the README** — the usual starting state. *Fix*: README keeps
  what/quick start/test/layout; the rest moves to `docs/` with links.

## Applying it to a small project

Do not build all four sections for a 500-line tool. Scale it:

- **Small tool**: README (what, quick start, configuration reference table) is
  the whole documentation set.
- **Growing library**: README + generated API reference + two or three how-to
  guides for the common tasks.
- **Team service**: all four, plus ADRs, plus a runbook (which is a how-to guide
  written for an incident: symptom, diagnosis, action).

The framework is a diagnostic tool, not a mandatory folder structure. Its value
is the question it makes you ask: *what is my reader doing right now?*
