# Profiling by ecosystem

Read the section for your stack. The goal of every tool below is the same:
find the one or two things that account for most of the cost, before changing
anything.

## Contents
- [Reading a profile](#reading-a-profile)
- [Python](#python)
- [Node / TypeScript](#node--typescript)
- [Go](#go)
- [Rust](#rust)
- [JVM](#jvm)
- [Databases](#databases)
- [Whole-system and production](#whole-system-and-production)

## Reading a profile

Two numbers appear in every profiler under different names:

- **Inclusive / cumulative / total**: time in this function *and everything it
  called*. Use it to find which subsystem is responsible.
- **Exclusive / self / flat**: time in this function's own code. Use it to find
  the hot function to actually change.

A function with high inclusive and near-zero exclusive time is a router — the
cost is below it. Follow the chain down until exclusive time appears; that is
where the work happens.

**Flame graphs** show the call stack as stacked bars, width proportional to
time. Read them for *width*, never for height: a wide bar is expensive, a tall
stack is merely deep. Look for wide plateaus — those are where the time is.

Before trusting any profile, check that the workload is representative. A
profile of a 100-row run tells you about startup costs, not about the quadratic
loop that appears at 100,000 rows.

## Python

```bash
python -m cProfile -s cumtime script.py | head -40   # deterministic, whole run
pyinstrument script.py                               # readable call tree, low overhead
py-spy top --pid 1234                                # live process, no restart, prod-safe
py-spy record -o flame.svg --pid 1234                # flame graph from production
python -X importtime script.py                       # slow startup
```

- `cProfile` adds noticeable overhead and distorts many small calls; use it for
  a first orientation, then confirm with a sampling profiler.
- `pyinstrument` shows the call tree with time attribution and is usually the
  fastest way to see the shape of the problem.
- `py-spy` attaches to a running process without modifying or restarting it,
  which makes it the right tool for a production mystery.
- Memory: `tracemalloc` (stdlib, allocation sources), `memray` (full profile
  with flame graphs), `objgraph` for reference cycles.
- Line-level: `line_profiler` (`@profile` decorator) once you know the function.
- Timing two implementations: `timeit`, and `pytest-benchmark` to track in CI.

## Node / TypeScript

```bash
node --cpu-prof --cpu-prof-dir=./prof app.js   # writes a .cpuprofile for DevTools
node --heap-prof app.js                        # heap allocation profile
clinic doctor -- node app.js                   # diagnoses event-loop vs CPU vs I/O
0x app.js                                      # flame graph
```

- Load the `.cpuprofile` into Chrome DevTools (Performance tab) for a flame
  chart with source mapping.
- **Event-loop lag is the metric that matters** for a Node service: it means
  something synchronous is blocking. `clinic doctor` identifies this directly,
  and it is the most common Node performance bug.
- `perf_hooks.performance.now()` for targeted timing; `--trace-sync-io` to find
  synchronous filesystem calls on the hot path.
- Browser: the Performance panel for runtime, Lighthouse for page load, and the
  Coverage tab to find unused JS/CSS.

## Go

Go's tooling is the best of any ecosystem — use it.

```go
import _ "net/http/pprof"   // then: go tool pprof http://localhost:6060/debug/pprof/profile
```

```bash
go test -bench=. -benchmem -cpuprofile=cpu.out -memprofile=mem.out ./...
go tool pprof -http=:8080 cpu.out      # interactive flame graph in the browser
go tool trace trace.out                # scheduler, goroutine blocking, GC
```

- `-benchmem` reports allocations per operation. **Allocation count is often a
  better optimisation target than time** — it is more stable across machines and
  drives GC pressure.
- `pprof` supports CPU, heap, goroutine, mutex, and block profiles. A goroutine
  profile showing thousands of goroutines is a leak; a block profile shows
  contention.
- `benchstat` compares two benchmark runs with statistical significance, which
  is how you avoid reporting noise as an improvement.

## Rust

```bash
cargo bench                          # criterion: statistical, with regression detection
cargo flamegraph                     # flame graph via perf
perf stat ./target/release/app       # cache misses, branch mispredictions, IPC
```

- **Always profile a release build.** Debug builds are 10-100× slower and the
  profile is meaningless.
- `criterion` reports confidence intervals and flags regressions against the
  previous run — it will tell you when a "win" is noise.
- `dhat` or `heaptrack` for allocations; `cargo-bloat` for binary size.
- Check for accidental `clone()` in hot paths and `Vec` reallocation
  (`with_capacity` when the size is known).

## JVM

```bash
java -XX:+FlightRecorder -XX:StartFlightRecording=duration=60s,filename=app.jfr -jar app.jar
```

- **Java Flight Recorder + JDK Mission Control** is the production-safe default:
  very low overhead, and it captures allocation, locks, GC, and I/O together.
- `async-profiler` for accurate flame graphs (it avoids the safepoint bias that
  makes older sampling profilers point at the wrong methods).
- GC logs (`-Xlog:gc*`) when latency has spikes rather than a high mean — that
  pattern is almost always GC or lock contention, not slow code.
- JMH for microbenchmarks. Do not hand-roll JVM microbenchmarks: JIT warmup and
  dead-code elimination will give you a confidently wrong answer.

## Databases

The database is where most application latency actually is, and no CPU profiler
will show it to you.

```sql
EXPLAIN (ANALYZE, BUFFERS) SELECT ...;   -- Postgres: real timings and I/O
```

Read the plan for:

- **Sequential scan on a large table** where you expected an index scan. Often a
  missing index, a type mismatch in the predicate, or a function applied to the
  column.
- **Rows estimated vs actual** far apart — stale statistics, and the planner is
  choosing badly as a result.
- **Nested loop over many rows** where a hash join would be right.
- **Sort or hash spilling to disk** — needs more `work_mem` or a smaller
  intermediate result.

Also: enable slow-query logging in production and read it weekly; count queries
per request (an N+1 is invisible in a plan because each individual query is
fast); and check index usage statistics to find indexes that cost writes and
serve no reads.

## Whole-system and production

- **Distributed tracing** (OpenTelemetry, Jaeger, Datadog) is the only way to
  see where time goes across services. Instrument the boundaries first — that is
  where the surprises are.
- **RED metrics** per endpoint: Rate, Errors, Duration — with p50/p95/p99. Alert
  on the tail, not the mean.
- **Continuous production profiling** (Pyroscope, Cloud Profiler, Datadog) runs
  at a few percent overhead and answers "what was it doing at 3am" without
  reproducing the load.
- `perf`, `strace`, `iostat`, `vmstat` when you suspect the layer below your
  runtime — a process that is slow while showing low CPU is usually waiting on
  I/O, a lock, or the network.
- Always compare against a **baseline captured under the same conditions**.
  Production numbers from Tuesday and Saturday are not comparable.
