# Profiling Node / TypeScript

Profiling Node / TypeScript: the tools, and what to look for in their output.
Read this alongside reading-a-profile.md if you have not read a profile
before.

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
