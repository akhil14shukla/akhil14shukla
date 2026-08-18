# Designing for performance before there is anything to profile

Read this when the shape of a system is still being decided — a new service, a
new endpoint, a schema, a page — or when profiling has told you the bottleneck is
structural and no local fix will reach the target.

## Contents
- [The ceiling is set at design time](#the-ceiling-is-set-at-design-time)
- [Latency budgets](#latency-budgets)
- [Chattiness is the usual culprit](#chattiness-is-the-usual-culprit)
- [Separate the read path from the write path](#separate-the-read-path-from-the-write-path)
- [Schema and indexes are performance decisions](#schema-and-indexes-are-performance-decisions)
- [Cache layers, by distance](#cache-layers-by-distance)
- [Frontend: the numbers users are measured against](#frontend-the-numbers-users-are-measured-against)
- [Capacity on the back of an envelope](#capacity-on-the-back-of-an-envelope)
- [Cost is a performance metric](#cost-is-a-performance-metric)

## The ceiling is set at design time

Profiling optimises within a design; it cannot escape one. If an endpoint makes
six sequential network calls, no amount of CPU tuning gets it under the sum of
those six round trips — that number is fixed by the shape, not the code. The
decisions below set the ceiling; everything in `SKILL.md` operates beneath it.

Three questions answer most design-time performance concerns:

1. **How many network round trips does one user action cost?** Each one is worth
   more than millions of in-memory operations. Count them; the count is your
   floor.
2. **How much data crosses each boundary, and how much of it is used?** Fetching
   a 400KB object to render three fields is a decision, and it repeats on every
   request.
3. **What grows?** Which of these is O(users), O(rows), O(items in a cart)? The
   thing that grows is where the design will fail, and it is rarely the thing
   that is slow today.

## Latency budgets

Give the user-facing operation a total, then divide it among its parts. Without
this, every component is "fast enough" on its own and the sum is 4 seconds.

```
GET /orders/{id}          budget 300ms p95
├── auth check             20ms   (cached, in-process)
├── load order             40ms   (indexed primary-key read)
├── load line items        40ms   (one query, not one per line)
├── pricing calculation    30ms   (pure, in-process)
├── inventory service     120ms   (network — the dominant cost, and the risk)
└── serialise + transfer   50ms
```

Two rules follow, and both matter more than they look:

- **A nested call's timeout must fit inside the caller's remaining budget.** If
  your endpoint must answer in 300ms, a downstream call cannot have a 5s
  timeout — by the time it fires, the caller has already given up and the work
  is wasted. Propagate a deadline (a context, a cancellation token) rather than
  hardcoding a timeout per call.
- **The budget names the thing to design around.** Above, the inventory call is
  40% of the budget and the only network hop. That is the piece to make
  optional, cacheable, or parallel — and knowing that before writing the code is
  worth more than any later optimisation.

## Chattiness is the usual culprit

Almost every structurally slow system is chatty: many small round trips where
one larger one would do.

- **N+1 in all its forms** — a query per row, an HTTP call per item, a file read
  per record, a cache lookup per field. Design the batch interface first:
  `getUsers(ids)` rather than `getUser(id)` called in a loop.
- **Sequential when it could be concurrent.** Three independent calls taking
  100ms each cost 300ms sequentially and 100ms in parallel. Only parallelise
  genuinely independent work, and bound it.
- **Chatty interfaces across a boundary you might later distribute.** A
  fine-grained interface is free in-process and ruinous over a network. If a
  module might become a service, design its interface as coarse operations now
  — this is the practical reason `repo-architect` insists module boundaries use
  explicit, coarse interfaces.
- **Payload shape.** Return what the caller needs. An endpoint that returns a
  deep object graph because "it might be useful" pays serialisation, transfer,
  and parse cost on every call forever.

## Separate the read path from the write path

Most systems read far more than they write, and the two want opposite things:
writes want normalisation and constraints, reads want everything in one place.

Escalate only as far as the problem requires:

1. **Indexes and query tuning** — nearly always enough.
2. **A read replica** — reads scale out; accept replication lag and route
   read-after-write to the primary.
3. **A denormalised read model or materialised view** — precomputed answers for
   an expensive query, refreshed on write or on a schedule.
4. **Full CQRS with separate stores** — genuinely useful at scale, and a large
   permanent increase in complexity. Rare that it is the right answer.

Each step buys speed with staleness or complexity. Name which you are paying,
and say what the acceptable staleness is — that is a product decision, not a
technical one.

## Schema and indexes are performance decisions

Made once, felt forever, and expensive to change on a large table.

- **Model by how it will be queried**, not only by how it is conceptually
  structured. Write the three most important queries before finalising the
  schema.
- **Index what you filter, join, and sort on.** A composite index's column order
  matters: it serves queries that use a *prefix* of its columns, so
  `(tenant_id, created_at)` serves `WHERE tenant_id = ?` and
  `WHERE tenant_id = ? ORDER BY created_at`, but not `WHERE created_at > ?`
  alone.
- **Every index costs write throughput and storage.** Unused indexes are pure
  loss — check usage statistics and drop them.
- **Know what prevents index use**: a function applied to the column
  (`WHERE lower(email) = ?` needs a matching expression index), a leading
  wildcard `LIKE '%x'`, and an implicit type cast in the predicate.
- **Plan for size.** A table that will hold 500M rows wants partitioning decided
  up front — retrofitting it on a live table is a migration project. Decide the
  retention and archival policy at design time; "we keep everything forever" is
  a choice with a cost.
- **Verify with `EXPLAIN ANALYZE` against production-sized data.** Everything is
  fast on the 200-row dev table.

## Cache layers, by distance

Cache as close to the consumer as correctness allows; each layer removes work
from everything behind it.

| Layer | Latency | Good for | Watch out for |
|---|---|---|---|
| Browser / HTTP cache | 0 | Static assets, immutable content | Cache-busting on deploy |
| CDN | ~10ms | Public, cacheable responses | Per-user data must never land here |
| In-process memory | ~0.1µs | Small hot config, compiled artefacts | Per-instance, so inconsistent across a fleet |
| Shared cache (Redis) | ~1ms | Session, computed results, rate limits | A network hop; needs eviction and a bounded size |
| Materialised view | query cost | Expensive aggregates | Refresh strategy and staleness |

Design the invalidation *with* the cache, not after. And never cache per-user
data under a key that omits the user — that is a data-leak bug wearing a
performance costume.

## Frontend: the numbers users are measured against

Web performance is measured in the field, at the 75th percentile of real users,
against three thresholds:

| Metric | Good | What it measures | Usually caused by |
|---|---|---|---|
| **LCP** | < 2.5s | Time until the largest visible element paints | Slow server response, render-blocking CSS/JS, unoptimised hero images |
| **INP** | < 200ms | Responsiveness to interaction, across the visit | Long JavaScript tasks blocking the main thread |
| **CLS** | < 0.1 | Unexpected layout movement | Images and ads without reserved dimensions, late-injected banners, font swaps |

Set your budget at ~80% of each threshold (LCP 2.0s, INP 160ms, CLS 0.08) so a
regression is caught before it fails. INP is the most commonly failed of the
three, and the fix is almost always the same: break up long main-thread tasks,
defer non-critical JavaScript, and stop shipping work the first paint does not
need.

Structural choices that dominate all three: how much JavaScript ships at all
(set a byte budget and enforce it in CI), whether the first paint requires a
round trip for data, whether images are correctly sized and given explicit
dimensions, and whether fonts are preloaded with a sane fallback. Measure in the
field (real user monitoring), not only in the lab — lab tools run on a fast
machine on a fast network and will tell you everything is fine.

## Capacity on the back of an envelope

Before building, do the arithmetic. It takes two minutes and routinely changes
the design.

```
1M daily active users × 20 requests/day  = 20M requests/day
20M / 86,400s                            ≈ 230 requests/second average
peak ≈ 3-5× average                      ≈ 1,000 requests/second
each request: 2 queries × 1ms            = 2,000 queries/second at the database
each response 20KB                       ≈ 20 MB/s egress ≈ 50 TB/month
```

Now you know whether this is a single-instance problem or a fleet problem, and
whether the database is comfortable or the constraint — before writing code.
Redo the sum for the growth case: what breaks at 10×? The component that breaks
first is the one whose design deserves the most thought.

## Cost is a performance metric

Cloud spend is latency's twin: both are consequences of how much work the system
does. When someone asks to cut the bill, the technique is identical — measure,
find the dominant line item, fix that.

- **Measure cost per unit of work** (per request, per tenant, per job), not just
  the monthly total. Only the per-unit number tells you whether growth or
  inefficiency is driving the bill.
- **The usual dominant items**: egress bandwidth, always-on over-provisioned
  compute, unpartitioned queries scanning whole tables, log and metric volume
  charged per GB ingested, and storage nobody deleted.
- **Idle capacity is the most common waste.** Right-size from observed usage,
  and use autoscaling with a floor you have actually justified.
- **A cheaper algorithm is a cheaper bill.** Removing an N+1 cuts database CPU,
  which is often a larger line item than the application tier.
- Sampling traces and logs, and setting retention deliberately, frequently cuts
  observability spend by an order of magnitude with no loss of usefulness.
