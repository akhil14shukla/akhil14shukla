# Profiling Go

Profiling Go: the tools, and what to look for in their output. Read this
alongside reading-a-profile.md if you have not read a profile before.

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
