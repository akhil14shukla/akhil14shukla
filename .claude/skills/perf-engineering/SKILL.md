---
name: perf-engineering
description: Make code measurably faster without making it unreadable — set a target, profile to find the dominant cost, fix the biggest one, prove the win. Covers algorithmic complexity, data structures, N+1 and I/O batching, caching, memory, concurrency, and honest benchmarking. Use whenever something is slow, expensive, or memory-hungry: "this is too slow", "optimise this", "reduce latency", "it times out", "high memory usage", "cut our cloud bill", "the page is slow", "Core Web Vitals", or when designing an endpoint, schema, or page whose speed will matter. Also use before accepting any optimisation, to check it was actually measured.
---

# Performance engineering

Almost all wasted optimisation effort comes from one mistake: **changing code
before knowing where the time goes.** Intuition is unreliable in every language,
because cost concentrates in places that do not look expensive — a linear scan
inside a loop, a query per row, a serialisation boundary crossed a million
times.

## The loop

1. **Set a target.** "p95 under 150ms at 3k rps." "Under 30s for 2M rows."
   Without a number you cannot tell when to stop, and you will keep going until
   the code is unreadable. If nobody gave you one, propose it from the real
   constraint and say what you assumed.
2. **Measure the baseline on representative data.** Toy data hides the problem
   entirely — an O(n²) loop is instant at n=100 and fatal at n=100,000. Record
   the number; you cannot claim an improvement without it.
3. **Profile to find the dominant cost.** Not "read the code and guess". Use
   inclusive time to find the responsible subsystem, exclusive time to find the
   hot function. Know what your profiler cannot see: a CPU profiler shows
   nothing for time spent *waiting* on a database or an HTTP call, which is
   where most real application latency lives.
4. **State a hypothesis and the expected win.** "The N+1 costs ~400 queries per
   request; batching should halve p95." A prediction makes the result
   informative even when you are wrong.
5. **Make the smallest change that tests it.** One change — not a rewrite
   bundled with three speculative improvements, or you cannot attribute the
   result.
6. **Re-measure the same way. If the number did not move, revert.** Complexity
   that buys nothing is a permanent tax, and the next reader will assume it was
   necessary and preserve it.
7. **Leave the evidence in a comment**, so nobody simplifies it back out:
   `# Batched into one query: 412 queries → 2, p95 380ms → 46ms on the 10k fixture.`

## Where the wins actually are

Work down this list; do not start at the bottom.

1. **Do less work** — a better algorithm, or filter earlier. Reducing O(n²) to
   O(n log n) beats any constant-factor tuning. Most accidental quadratics look
   innocent: a membership test against a list inside a loop, a `.find()` inside
   a `.map()`, string concatenation in a loop.
2. **Do it fewer times** — batching, caching, killing N+1. This is the biggest
   real-world win in application code and is almost never what a CPU profile
   points at. **A single network round trip costs more than millions of
   in-memory operations**, so any change removing one beats almost any CPU
   tuning. Look for a loop containing I/O of any kind.
3. **Do it at a better time** — off the request path, lazily, or precomputed.
   Total work is unchanged but the latency a user feels is not.
4. **Do it in parallel** — only after the above, since parallelising wasteful
   work just wastes resources faster, and it buys real complexity.
5. **Make each operation faster** — allocations, memory layout, tighter loops.
   Real, but usually a few percent, and it costs readability. Justify each with
   a measurement.

## When no local fix will reach the target

Profiling optimises *within* a design; it cannot escape one. An endpoint making
six sequential network calls cannot get under the sum of those six round trips,
whatever you do to the code between them. When the profile keeps pointing at
"waiting", when the biggest cost is the number of round trips rather than any
one of them, or when you are designing something whose speed will matter before
any code exists, the decisions that set the ceiling are in
`references/design-for-performance.md` — latency budgets, chattiness, read/write
split, schema and index design, cache layers, frontend vitals, capacity
arithmetic, and cost.

## Knowing when to stop

Stop at the target. Then say what you did, what it bought, and what you
deliberately left: "the rest is in JSON serialisation; a binary format would cut
another 15% but changes the public API, so I left it."

Do not trade readability for a win you cannot measure. An optimisation that
doubles the difficulty of reading for 3% needs justifying out loud, and usually
should not be made.

## Read the reference that matches your task

| If you are… | Read |
|---|---|
| Designing an endpoint, schema, or page — or the bottleneck is structural | `references/design-for-performance.md` |
| About to profile, or reading a profile or `EXPLAIN` output | `references/profilers/` — `reading-a-profile` first, then `python`, `node`, `go`, `rust`, `jvm`, `databases`, `production` |
| Fixing a known bottleneck — data structures, I/O, caching, memory, concurrency, or benchmarking | `references/techniques.md` |
| Considering replicas, queues, backpressure, pool sizing, rate limiting, or sharding | `references/scaling.md` |

For language-specific detail, load `python-engineering` and read its performance
reference, or `code-craft` and read its per-language reference.
