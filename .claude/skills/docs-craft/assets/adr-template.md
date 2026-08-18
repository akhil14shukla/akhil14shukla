# NNNN: <short decision title in the imperative>

<!-- File name: docs/adr/0007-use-postgres-for-the-event-store.md
     Numbered sequentially. Never edited after acceptance — a decision that is
     replaced gets "Status: Superseded by NNNN" and stays, because the history
     is the value. -->

**Status:** Proposed | Accepted | Deprecated | Superseded by [NNNN](NNNN-title.md)
**Date:** YYYY-MM-DD
**Deciders:** <who was in the room>

## Context

<!-- The forces at play, factually and without arguing for the outcome yet:
     the requirement driving this, constraints (scale, budget, deadline,
     compliance), what the team already knows and already runs, and what
     happens if we do nothing.

     A reader in two years should be able to tell whether these forces still
     hold — which is how they know whether to revisit the decision. -->

## Decision

<!-- What we will do, stated actively and specifically:
     "We will store events in Postgres in a single append-only table
     partitioned by month, accessed through a repository interface."

     Specific enough that someone can tell whether the code follows it. -->

## Consequences

<!-- What becomes easier, what becomes harder, and what we accept.

     Include the bad parts honestly — an ADR listing only benefits is not
     believed, and the costs are exactly what a future reader needs to weigh. -->

**Positive**
-

**Negative / accepted costs**
-

**Follow-up required**
- <!-- Anything this decision obliges us to do later: revisit at a scale
       threshold, add monitoring, migrate an existing system. -->

## Alternatives considered

<!-- Each realistic option and the specific reason it was not chosen. This is
     the section that stops the decision being re-litigated every six months. -->

### <Alternative A>
Rejected because: <specific reason tied to the context above>

### <Alternative B>
Rejected because:

## References

<!-- Benchmarks, prototypes, issues, vendor docs, prior art the decision rests
     on. -->
