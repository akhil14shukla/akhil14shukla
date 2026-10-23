# Building a case catalogue for any domain

Read this when deciding *which* scenarios to write for an application — before
the first batch, or when auditing a suite for gaps. It is a method, not a list:
apply it to the domain, and record the result as a catalogue table in
`e2e/README.md`. The method produces the catalogue; do not start from another
domain's list. (If a use-case pack's domain matches the app, its catalogue is a
valid starting point — see `use-cases/README.md`.)

## Contents

1. Where cases come from
2. Six lenses that find the cases people miss
3. Policy questions: when the answer is not yours
4. The catalogue table
5. Priority order for the first suite
6. Auditing an existing suite

## 1. Where cases come from

Mine these in order; each is cheaper and more reliable than imagining cases:

1. **Incidents and production bugs** of the last 12–24 months, with their
   tickets. These already cost money; every one becomes a `REG` scenario.
2. **The manual regression checklist** the team runs before releases. Each line
   is a scenario; this is the work being automated away.
3. **Error logs of each external integration**: every distinct error message an
   external system has returned is a failure mode to stub.
4. **Support tickets and user-reported "weird" cases** — they reveal real input
   shapes (typos, truncation, encodings).
5. **The code's own branches** on the paths under test: every `if`, `case`,
   validation rule and exception handler is a rule someone thought mattered.
6. **Specifications and acceptance criteria**, if they exist and are current.

## 2. Six lenses that find the cases people miss

Apply each lens to every entity and every integration call in the flow.

**State machine.** Draw each core entity's states and transitions (from the
status column and the code that writes it). One scenario per valid transition;
one per *invalid* transition that a user or job could attempt (acting on an
already-completed, cancelled, or failed item). Invalid transitions are where
double-processing bugs live.

**Boundaries.** For every limit (amount, tolerance, quantity, length, date,
period, retry count): exactly at it, one unit inside, one unit outside. For
dates: the last instant of a period and the first of the next, in the company's
time zone.

**Equivalence classes of input.** Group inputs that should behave the same and
take one representative per group, plus the ugly ones: empty, null, zero,
negative, very large, wrong type, wrong currency/unit, extra whitespace,
mixed case, Unicode look-alikes, truncated references.

**Decision tables for policies.** Where an outcome depends on several
conditions (customer status × amount × configuration), list the combinations
that produce *different* outcomes and write one scenario per distinct outcome.

**Integration failure modes.** For every call that changes external state, walk
`external-services.md` §6 row by row. Always include the unknown-outcome case
(§7 there).

**Re-runs and concurrency.** For every job and every user action: run it twice
(idempotency), run it over already-processed data (no changes), run two that
compete for the same row (no over-allocation), change the underlying data
between two steps (re-validation).

## 3. Policy questions: when the answer is not yours

Many cases have no technically correct answer — the business decides
(rounding rule, allocation order, what happens after a timeout). Mark such rows
*Policy* and write the question next to them. Ask the owner in one batch, with
the scenario each answer unblocks. Never encode the current code's behaviour as
the expectation for a *Policy* row without the owner confirming it; that is how
a suite ends up guarding bugs.

## 4. The catalogue table

```markdown
| ID | Case | Expected | Source | Status |
|---|---|---|---|---|
| ORD-PAY-004 | Provider declines the charge | Order unpaid, reason stored, no shipment call | INC-2291 | ✓ |
| ORD-PAY-007 | Charge times out after send | Order parked for reconciliation, never charged twice | lens: failure modes | ✓ |
| ORD-ALLOC-010 | Stock exactly at reorder threshold | *Policy*: reorder at ≤ or < threshold? | lens: boundaries | blocked (Q3) |
```

`Status`: ✓ written and passing · ✗ written, exposes a bug (ticket) · skip
(quarantined, ticket) · blocked (policy question) · todo.

## 5. Priority order for the first suite

1. **One happy path per stage** of the flow, to prove the wiring.
2. **Every incident and production bug** (`REG`).
3. **Integrity cases**: anything that can duplicate or lose money, stock, or
   records — double submission, unknown outcomes, re-runs, over-allocation,
   wrong tenant/company.
4. **Every distinct external error** seen in production logs.
5. **Policy boundaries** once their questions are answered.
6. Everything else, ordered by how often manual testers check it today.

Thirty to fifty scenarios covering 1–4 typically replace most of a manual
regression pass.

## 6. Auditing an existing suite

- **Mutation round** (`adoption-playbook.md` Phase 6): inject realistic bugs;
  each that survives is a missing scenario.
- **Lens sweep**: for each entity, check that every state transition and every
  integration call has at least one negative scenario.
- **Assertion sweep**: every negative scenario has `db_unchanged` and a
  `count: 0` on external calls; every external-state-changing scenario asserts
  the payload.
