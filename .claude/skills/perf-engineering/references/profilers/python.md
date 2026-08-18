# Profiling Python

Profiling Python: the tools, and what to look for in their output. Read this
alongside reading-a-profile.md if you have not read a profile before.

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
