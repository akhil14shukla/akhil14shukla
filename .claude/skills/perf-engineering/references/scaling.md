# Scaling patterns and their failure modes

When one process tuned well is not enough. Each pattern below buys something and
costs something — the cost is usually a new failure mode, so it is listed too.

## Contents
- [Scale up before scaling out](#scale-up-before-scaling-out)
- [Read replicas](#read-replicas)
- [Queues and background work](#queues-and-background-work)
- [Backpressure and load shedding](#backpressure-and-load-shedding)
- [Connection pool sizing](#connection-pool-sizing)
- [Rate limiting](#rate-limiting)
- [Sharding and partitioning](#sharding-and-partitioning)
- [The checklist before you scale anything](#the-checklist-before-you-scale-anything)

## Scale up before scaling out

A bigger machine is almost always cheaper than a distributed system, once you
count engineering time, operational complexity, and the new failure modes.
Modern single machines handle far more than most teams assume.

Scale out when you need availability across failure domains, when you have
genuinely outgrown one machine, or when workloads need isolation. Not because it
sounds more serious.

## Read replicas

Move read traffic off the primary. Cheap and effective when reads dominate.

**The cost: replication lag.** A user writes, is redirected to a read, and their
own change is missing — the classic "I saved it and it disappeared" bug. Route
reads that must be consistent (anything immediately after a write by the same
user) to the primary, and be explicit in the code about which reads tolerate
staleness.

## Queues and background work

Moving work off the request path is the highest-leverage latency change
available: the user waits for the acknowledgement, not the work.

Good candidates: emails, exports, thumbnails, webhooks, analytics, anything
retryable and not needed in the response.

The costs, all of which must be designed for:

- **Jobs run more than once.** Every consumer must be idempotent — a retried
  charge is a double charge.
- **Jobs fail invisibly.** You need a dead-letter queue and an alert on it, or
  failures accumulate silently for weeks.
- **Queues grow.** Monitor depth and age-of-oldest-message; a growing queue means
  consumers cannot keep up and is the earliest warning of an outage.
- **Ordering is not guaranteed** unless you pay for it. Do not assume job B runs
  after job A.

## Backpressure and load shedding

A system without backpressure fails by falling over entirely instead of
degrading. When demand exceeds capacity you must choose what to drop, or the
system chooses for you — badly, by exhausting memory.

- **Bound every queue and buffer.** Unbounded means "we will OOM instead of
  rejecting", which is strictly worse than rejecting.
- **Shed load early.** Reject at the edge with a 429 and a `Retry-After` rather
  than accepting work you cannot finish. A fast rejection is a better user
  experience than a timeout, and it protects everything downstream.
- **Time out everything**, with budgets that shrink as you go deeper. If the
  caller has already given up, work in progress is pure waste — cancel it.
- **Circuit-break failing dependencies.** Retrying into a dead service converts
  their outage into yours and prevents their recovery.
- **Prioritise**: shed low-value traffic (bulk exports, analytics) before
  user-facing requests.

## Connection pool sizing

A recurring and expensive mistake: pool size is not "as large as possible". Each
connection consumes memory and a worker on the database, and past the point of
saturation more connections make everything slower through contention.

Start from the database's capacity, not the application's concurrency. Total
connections across *all* application instances must stay within what the
database can serve. A common starting point for a relational database is a small
multiple of its core count; measure and adjust.

Symptoms of a bad pool: connection-acquisition timeouts under load (too small,
or connections leaked), and database CPU dominated by context switching (too
large). Instrument pool wait time — it is the number that tells you which.

## Rate limiting

Protects you from one caller's mistake and makes capacity predictable.

- **Token bucket** for smooth limiting that allows short bursts; **sliding
  window** for accurate per-period quotas; **fixed window** is simplest and has a
  boundary-burst problem (double the limit across a window edge).
- Limit per *tenant*, not globally, or one heavy user degrades everyone.
- Return `429` with `Retry-After` and document the limit — an undocumented limit
  is indistinguishable from a bug to the caller.
- Rate-limit your own outbound calls too, or you become the abusive client.

## Sharding and partitioning

The last resort, because it changes everything: cross-shard queries, transactions
across shards, and rebalancing are all hard, and choosing a shard key wrongly is
expensive to undo.

Exhaust these first: indexing, query tuning, caching, read replicas, archiving
old rows, and a bigger machine. When you do shard, choose a key that distributes
evenly and keeps related data together (usually tenant/customer id), and expect
hot shards anyway.

Table partitioning within one database is a much cheaper intermediate step for
large time-series tables — it makes deleting old data instant and keeps indexes
smaller.

## The checklist before you scale anything

1. Have you profiled, or are you scaling to avoid finding the problem? Adding
   machines to hide an N+1 query is the most expensive way to fix it.
2. Is there an index missing? This is the single most common answer.
3. Is there an N+1 in the hot path?
4. Are you fetching more data than you use?
5. Is there an obvious cache with a simple invalidation story?
6. Can this work move off the request path?
7. Only then: more machines, replicas, or shards.
