# Whole-system and production profiling

Whole-system and production profiling: the tools, and what to look for in
their output. Read this alongside reading-a-profile.md if you have not read a
profile before.

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
