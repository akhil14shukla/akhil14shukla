---
name: perf-engineering
description: Make code measurably faster without making it unreadable — set a target, profile to find the dominant cost, fix the biggest one, and prove the win. Covers algorithmic complexity, data structure choice, N+1 and I/O batching, caching with a real invalidation story, memory and allocation, concurrency, and honest benchmarking. Use this whenever something is slow, expensive, or memory-hungry: "this is too slow", "optimise this", "reduce latency", "it times out", "high memory usage", "cut our cloud bill", "why is this endpoint slow", or when a change is about to touch a hot path. Also use before accepting any optimisation, to check it was actually measured.
---

# Performance engineering

Almost all wasted optimisation effort comes from one mistake: **changing code
before knowing where the time goes.** Intuition about performance is unreliable
in every language, because cost concentrates in places that do not look
expensive — a linear scan inside a loop, a query per row, a serialisation
boundary crossed a million times.

The discipline below exists to stop you rewriting a function that accounts for
2% of runtime.

## The loop

Work through these in order. Skipping step 1 or 2 is what produces slower,
uglier code.

**1. Set a target.** "The report must finish in under 30s for 2M rows." "p95
latency under 150ms at 3k requests/second." "Memory under 512MB." Without a
number you cannot tell when to stop, and optimisation has no natural end — you
will keep going until the code is unreadable.

If nobody has given you a number, propose one from the actual constraint (a user
waiting, a cron window, a container memory limit) and say what you assumed.

**2. Measure the baseline on representative data.** Toy data hides the entire
problem: an O(n²) loop is instant at n=100 and fatal at n=100,000. Record the
number before you change anything — you cannot claim an improvement without it.

**3. Profile to find the dominant cost.** Not "read the code and guess" — run a
profiler and read the output. You are looking for the one or two things that
account for most of the time. Look at inclusive time to find the responsible
subsystem, then exclusive time to find the hot function.

Be aware of what your profiler cannot see: a CPU profiler shows nothing for time
spent *waiting* on a database or an HTTP call, which is where most real
application latency lives. For that you need request tracing, query logs, or
wall-clock timing around the calls.

**4. Form a hypothesis and state the expected win.** "The N+1 in the order
listing costs ~400 queries per request; batching should cut p95 by half." A
prediction makes the next step meaningful — if you were wrong, you have learned
something about the system instead of just landing a diff.

**5. Make the smallest change that tests the hypothesis.** One change. Not a
rewrite bundled with three speculative improvements, because then you cannot
attribute the result.

**6. Re-measure the same way.** If the number did not move meaningfully, **revert
it.** Complexity that buys nothing is a permanent tax on every future reader,
and the next person will assume it was necessary and preserve it.

**7. Leave the evidence in the code.** One comment: what you measured, before and
after.

```py
# Batched into one query keyed by order_id: 412 queries → 2, p95 380ms → 46ms
# on the 10k-order fixture. Do not revert to the per-row lookup.
```

That comment is what stops someone "simplifying" the optimisation back out next
quarter, and what tells a reviewer this was measured rather than guessed.

## Where the wins actually are

In rough order of payoff. Work down this list; do not start at the bottom.

**1. Do less work — a better algorithm or an earlier filter.**
Reducing O(n²) to O(n log n) beats any constant-factor tuning, and the gap widens
with scale. Most accidental quadratics look innocent: a membership test against a
list inside a loop, a `.find()` inside a `.map()`, string concatenation in a
loop, a nested loop over two collections. Filtering earlier — in the database,
before deserialisation, before the loop — is the same win from the other
direction: the cheapest work is work you never do.

**2. Do it fewer times — batching, caching, and killing N+1.**
This is the biggest real-world win in application code, and it is almost never
what a CPU profile points at. One query returning 1,000 rows beats 1,000
queries by orders of magnitude, because you are paying round-trip latency each
time. The same applies to HTTP calls, file reads, log writes, and cache
lookups. Look for a loop that contains any I/O at all — that is the pattern.

**3. Do it at a better time — asynchronously, lazily, or ahead of time.**
Work moved off the request path (a queue, a background job) removes it from the
latency the user feels even though total work is unchanged. Lazy evaluation
avoids work nobody asked for. Precomputation trades memory and staleness for
speed.

**4. Do it in parallel.** Only after the above: parallelising wasteful work just
wastes more resources faster. And parallelism adds real complexity — races,
ordering, partial failure — so it needs to buy something substantial.

**5. Make each operation faster.** Micro-optimisation: allocations, memory
layout, avoiding copies, tighter loops. Real, but usually a few percent, and it
costs readability. Justify each one with a measurement.

## Cost model: what is expensive

Orders of magnitude matter more than exact figures. Approximate, on modern
hardware:

| Operation | Rough cost | In practical terms |
|---|---|---|
| L1 cache reference | ~1 ns | free |
| Main memory reference | ~100 ns | 100× an L1 hit |
| Interpreted-language op (Python/Ruby) | ~10-100 ns | why loops in these languages hurt |
| SSD random read | ~100 µs | 1,000× a memory reference |
| Same-datacentre round trip | ~0.5 ms | 5,000× a memory reference |
| Database query (simple, local) | ~1 ms | |
| Cross-region round trip | ~50-150 ms | a whole latency budget |

The lesson: **a single network round trip costs more than millions of in-memory
operations.** Any change that removes a round trip beats almost any amount of
CPU tuning. This is why N+1 queries dominate real-world slowness, and why
"optimising" a loop that runs between two HTTP calls is usually pointless.

Second lesson: memory access patterns matter more than instruction counts in
tight numeric loops. Sequential access over a contiguous array is dramatically
faster than chasing pointers through scattered objects.

## Data structures

Most "slow code" is the wrong container. Before optimising anything else, check
these:

| If you are doing this | Use | Instead of |
|---|---|---|
| Checking membership repeatedly | hash set | scanning a list — O(1) vs O(n) |
| Looking up by key | hash map | list of pairs |
| Queue / sliding window | deque / ring buffer | array with shift/pop-front (O(n)) |
| Repeated min/max of a changing set | heap / priority queue | re-sorting |
| Top-k of many | bounded heap | full sort then slice |
| Range queries on sorted data | binary search | linear scan |
| Building a string in a loop | join/builder | `+=` (O(n²) for immutable strings) |
| Many small fixed-shape records | struct/array-of-values | map/dict per record |
| Large numeric arrays | typed array / dataframe | list of boxed numbers |

```
# The single most common real fix, in any language:
for user in users:                    # 10k users
    if user.id in banned_list:        # 50k-element list → 500M comparisons
        ...

banned = set(banned_list)             # build once, O(n)
for user in users:
    if user.id in banned:             # O(1) each → 10k operations
```

## I/O: where application latency lives

- **Kill N+1.** One query per parent row is the defining performance bug of ORM
  code. Fetch children in one query keyed by parent, or use the framework's
  eager loading (`selectinload`, `prefetch_related`, `JOIN FETCH`, `includes`).
  A useful, deterministic test: assert the query *count* for an endpoint.
- **Select only the columns you use.** `SELECT *` moves data you discard across
  the wire and prevents index-only scans.
- **Paginate everything that can grow.** An endpoint that returns "all" is a
  future outage, and it will happen on your biggest customer.
- **Push work into the database**: filtering, aggregation, sorting, and limits
  belong there. Fetching a million rows to count them in application code is the
  slowest possible `COUNT(*)`.
- **Index what you filter, join, and sort on** — and verify with `EXPLAIN
  ANALYZE` on production-sized data, not on the 200-row dev table where
  everything is fast.
- **Pool connections** and keep transactions short. Never hold a transaction open
  across a call to another service; that exhausts the pool and turns their
  latency into your outage.
- **Stream large payloads** rather than materialising them. Reading a 4GB file
  into memory is how a process gets OOM-killed.
- **Compress** what crosses a network boundary if it is large and compressible;
  it is usually a straight win over the wire.

## Caching

A cache is a correctness risk traded for speed. Add one only when you can answer
three questions: what invalidates it, what is the worst case if it is stale, and
what happens when it is empty.

- **Cache pure, expensive, repeatedly-requested things.** Caching something
  cheap adds lookup cost and complexity for nothing.
- **Bound every cache** — by size or TTL. An unbounded cache keyed on user input
  is a memory-exhaustion vector.
- **Prefer a short TTL to clever invalidation.** Explicit invalidation is where
  cache bugs live; 60 seconds of staleness is often perfectly acceptable and
  removes an entire class of bug.
- **Beware the stampede**: when a hot key expires, every request recomputes it
  simultaneously and takes down the thing you were protecting. Use a lock, a
  single-flight wrapper, or staggered expiry.
- **Never cache per-user data in a shared cache without the user in the key.**
  This is a data-leak bug, not a performance bug, and it is common.
- Know your layers — CPU cache, in-process memory, Redis, CDN, HTTP caching
  headers — and put the cache as close to the consumer as correctness allows.

## Memory

- **Streaming beats loading.** Process records as they arrive; keep memory flat
  regardless of input size. This is often also faster, because it stays in cache.
- **Watch for accidental copies** — slicing, string manipulation, serialising,
  passing large structures by value. In a loop, a copy becomes quadratic.
- **Allocation is not free.** In garbage-collected languages, allocation rate
  drives GC pressure and shows up as latency spikes rather than as CPU time.
  Reuse buffers in hot paths; preallocate when the size is known.
- **Leaks in managed languages are usually unbounded caches, registered
  listeners never removed, or a growing collection nobody prunes.** Look there
  first.
- Measure with a memory profiler and look at *allocation sources*, not just
  totals. Peak usage under concurrent load is the number that determines your
  container size.

## Concurrency

- **I/O-bound work parallelises well** — the waiting overlaps. This is where
  async/threads pay off.
- **CPU-bound work needs real parallelism**: multiple cores, processes, or a
  language without a global lock. Threads in a GIL-limited runtime buy nothing
  for pure computation.
- **Always bound concurrency.** Unlimited fan-out at a database or an API is a
  self-inflicted denial of service, and it makes *everything* slower through
  contention. Use a pool or semaphore sized to the downstream capacity.
- **More threads is not more throughput** past the point of contention. Measure;
  the optimum is often surprisingly low.
- Parallelism adds races, ordering issues, and partial failure. Only accept that
  cost for a measured, meaningful win.

## Benchmarking honestly

A benchmark that lies is worse than no benchmark — it justifies complexity that
does nothing.

- **Warm up** before measuring: JIT compilation, connection pools, caches, and
  page cache all make the first run unrepresentative.
- **Report the distribution, not one number.** For user-facing work p95 and p99
  are what people feel; a mean hides the tail. For micro-benchmarks the minimum
  is the cleanest signal, since noise only adds time.
- **Use production-shaped data.** Size, cardinality, sortedness, and cache-hit
  rate all change the answer. Sorted input hides a bad comparison function;
  all-unique keys hide a collision problem.
- **Change one thing at a time**, and re-run the baseline in the same session —
  machine state drifts between runs.
- **Beware measuring a cache.** The second run being fast may have nothing to do
  with your change.
- **Benchmark the whole operation**, not the function in isolation. Making a
  function 10× faster changes nothing if it is 3% of the request.
- In CI, track a benchmark over time and alert on a *percentage regression*.
  Absolute-time assertions in a test suite flake forever, because CI hardware
  varies.

## Knowing when to stop

Stop when you hit the target. Then say what you did, what it bought, and what
you deliberately left — "the remaining time is in JSON serialisation; moving to
a binary format would cut another 15% but changes the public API, so I left it."

Do not trade readability for a win you cannot measure. An optimisation that
makes the code twice as hard to read for 3% needs to be justified out loud, and
usually should not be made. If you keep it, comment it with the number.

## References

- `references/profilers.md` — how to profile in each ecosystem: Python, Node/TS,
  Go, Rust, JVM, plus database `EXPLAIN`, flame graphs, and production
  profiling. Read the section for your stack before profiling.
- `references/scaling.md` — patterns beyond a single process: read replicas,
  queues and backpressure, connection pool sizing, rate limiting, load shedding,
  and the failure modes each introduces.

Language-specific performance detail lives in the language skills: load
`python-engineering` and read its performance reference for Python, or
`code-craft` and read its per-language reference for everything else.
