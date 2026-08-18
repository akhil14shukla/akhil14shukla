# Cost model and the specific techniques

The concrete fixes, once profiling has told you where the time goes. Read the
section that matches your bottleneck rather than the whole file.

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
