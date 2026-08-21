# Attacking your own analysis

Read this when you have an answer and before you present it. The goal is to
find the flaw yourself, in ten minutes, rather than have a reviewer find it in
the meeting — or worse, have nobody find it.

Work through the attacks in order. Each is a specific way reconciliations are
wrong in practice, with the check that settles it.

## Attack 1 — The harness is wrong

Your comparison is code, and it has bugs at the same rate as any other code.

- **Identity control**: compare the ground truth with itself. Anything other
  than a perfectly clean result means the harness is broken, and every finding
  so far is unreliable.
- **Mutation control**: perturb one row of the candidate (change a value, drop a
  row, duplicate a key) and confirm the check reports exactly that. A check that
  cannot catch a planted error is not evidence about a real one.
- **Round-trip the loader**: re-export what you loaded and diff it against the
  input file. This catches silent type coercion, dropped columns, truncated
  precision, and rows lost to a malformed quote.
- **Recompute one row by hand**, end to end, from the raw source. One row done
  manually has caught more harness bugs than any amount of re-reading code.

## Attack 2 — The comparison is the wrong comparison

- Are both sides at the **same grain**, or did you aggregate one silently?
- Does the **scope** match — same date range, same entities, same statuses, same
  test-data exclusion?
- Are you comparing the **same metric**? "Revenue" has at least five definitions
  in most companies (gross, net of refunds, net of discounts, recognised,
  billed). Write the formula for each side and compare the formulas.
- Did the **join change the row count**? If yes, the arithmetic changed with it.
- Is the **direction** right — did you check both truth-only and candidate-only
  rows, or only the direction that was convenient?

## Attack 3 — The conclusion does not carry the numbers

- Do the explained causes **sum exactly** to the headline gap? If they sum to
  "about" it, at least one is mis-sized.
- Could two causes be **double-counting the same rows**? Intersect their row
  sets and check it is empty.
- Would the fix you are proposing actually **close the gap**? Simulate it:
  apply the correction and confirm the residual goes to zero.
- Does the cause **predict correctly out of sample**? A timezone hypothesis
  derived from January should also explain February. If it does not, it is a
  description of January, not a mechanism.

## Attack 4 — The pattern is an artefact

- **Simpson's paradox** — check every claim about a direction ("the candidate is
  consistently high") at segment level, since it can reverse per segment.
- **Survivorship** — you are only looking at rows that made it into both files.
  The rows that failed to load are invisible and are often exactly the broken
  ones. Check the loader's reject count, not just what it returned.
- **Selection by the very filter you are testing** — if the candidate was built
  by a filter you suspect, comparing only its rows cannot detect that filter.
- **Correlated dimensions** — "the difference is in EMEA" and "the difference is
  in EUR" may be the same fact. Cross-tab before claiming either.
- **Small-denominator ratios** — a 400% relative difference on a value of 0.02
  is noise, and will dominate a "worst offenders by percentage" list. Rank by
  absolute *and* relative, and report both.

## Attack 5 — The answer is too clean

- Zero differences: see "When a match is suspicious" in
  `references/statistical-checks.md` and run the mutation control.
- One cause explaining 100.0% of a multi-system gap is rare. Look once more for
  a second, smaller cause hiding inside the first.
- A residual of exactly zero after several adjustments is worth re-deriving from
  the raw totals — it is easy to construct a zero by subtracting a number from
  itself through two different paths.

## Attack 6 — The ground truth

Hold this until the others are done, because it is the explanation that is most
often reached for too early and most damaging when wrong.

- What independent evidence supports the truth being right here? A third source,
  a physical count, a bank statement, a customer-visible artefact.
- Is the truth authoritative for **this specific question**, or for a related
  one? (A ledger is authoritative for what was booked, not for what was
  shipped.)
- Has the truth itself been restated since the candidate was produced?
- If you do conclude the truth is wrong, say so with the same standard of proof
  you demanded of the candidate: mechanism, quantity, refutable test, and an
  independent confirmation.

## Attack 7 — The reader

- Could a reader reach a different conclusion from your own exhibits? If yes,
  address it in the write-up rather than hoping they do not.
- Is any number in the summary not traceable to a query, a script, or a file
  someone can re-run?
- Have you stated what you did **not** check, and what would change the answer?
  An analysis with no stated limits reads as either careless or overconfident,
  and one unmentioned gap costs more credibility than five disclosed ones.
