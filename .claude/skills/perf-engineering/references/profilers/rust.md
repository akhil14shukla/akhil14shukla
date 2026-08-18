# Profiling Rust

Profiling Rust: the tools, and what to look for in their output. Read this
alongside reading-a-profile.md if you have not read a profile before.

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
