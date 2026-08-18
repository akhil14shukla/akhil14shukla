# Profiling the JVM

Profiling the JVM: the tools, and what to look for in their output. Read this
alongside reading-a-profile.md if you have not read a profile before.

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
