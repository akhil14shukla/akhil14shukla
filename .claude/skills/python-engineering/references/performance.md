# Python performance: what is actually true

## Contents

- [The model in one page](#the-model-in-one-page)
- [The workflow](#the-workflow)
- [Cost of built-in operations](#cost-of-built-in-operations)
- [Choosing the data structure](#choosing-the-data-structure)
- [Doing less work](#doing-less-work)
- [Caching](#caching)
- [Streaming and memory](#streaming-and-memory)
- [Vectorising with numpy and polars](#vectorising-with-numpy-and-polars)
- [Micro-optimisations that are real](#micro-optimisations-that-are-real)
- [Concurrency and the GIL](#concurrency-and-the-gil)
- [Benchmarking honestly](#benchmarking-honestly)

## The model in one page

Guessing about Python performance is unusually unreliable, because the cost is
concentrated in places that do not look expensive. The reliable model:

**Every interpreted operation costs; C-implemented operations over many items
cost once.** So the wins, in the order they matter:

1. **Pick the right data structure.** Membership testing in a `list` is O(n);
   in a `set` or `dict` it is O(1). Turning a nested loop over two lists into a
   set lookup takes a 60-second job to under a second, and no micro-optimisation
   comes close.
2. **Do not do the work twice.** Hoist loop-invariant computation out of the
   loop. Cache pure, expensive, repeatedly-called functions with
   `functools.lru_cache`/`@cache`. Compute once, reuse.
3. **Push the loop into C.** `sum()`, `min()`, `max()`, `any()`, `sorted()`,
   `str.join`, `list.sort`, `bytes.translate`, `collections.Counter`,
   `itertools`, and numpy/polars operations run their iteration in C. A
   hand-written Python loop doing the same thing is typically several times
   slower.
4. **Batch your I/O.** One query returning 1000 rows beats 1000 queries by
   orders of magnitude — this (the N+1 pattern) is the most common real-world
   Python performance bug, and it is invisible in a profiler that only shows
   CPU. Same for HTTP calls, file reads, and log writes.
5. **Stream instead of materialising.** Generators and `itertools` keep memory
   flat; `list(f.readlines())` on a large file is how a process gets OOM-killed.
6. Only then micro-optimise: local-variable binding in hot loops, `__slots__`,
   avoiding attribute lookups in the innermost loop, `array`/`memoryview`.

Three specifics that come up constantly:

```py
# String building: O(n²) vs O(n). At 100k items this is seconds vs milliseconds,
# because each += copies the whole accumulated string.
out = ""
for s in parts: out += s          # slow
out = "".join(parts)              # fast

# Membership: O(n) per check vs O(1).
if user_id in banned_list:  ...   # list  → linear scan every call
banned = set(banned_ids)          # build once
if user_id in banned:  ...        # set   → constant time

# Repeated lookup in a hot loop: bind once outside it.
append = results.append            # avoids an attribute lookup per iteration
for x in data: append(transform(x))
```

**Measure before you optimise, and measure after.** `cProfile` for where the
time goes, `timeit` for comparing two implementations, `pyinstrument` or
`py-spy` for a readable call-tree of a real workload, `tracemalloc` or
`memray` for memory. Optimising an unmeasured guess usually makes the code
uglier and no faster — and reviewers will not be able to tell whether the
complexity bought anything. When you do optimise, leave a comment with the
number you measured.

`references/performance.md` has the full treatment: complexity of every
built-in operation, `lru_cache` pitfalls, numpy/polars vectorisation, when the
free-threaded 3.14 build actually helps, and how to benchmark honestly.
`perf-engineering` covers the language-agnostic methodology.

---

## The workflow

Never optimise from intuition. Python's costs are concentrated in places that do
not look expensive, and the usual guess is wrong.

1. **State the target.** "This report must finish in under 30s for a 2M-row
   input." Without a target you cannot know when to stop, and optimisation has
   no natural end.
2. **Measure the baseline** on realistic data. Toy data hides the problem — an
   O(n²) loop is instant at n=100 and fatal at n=100,000.
3. **Profile to find the dominant cost.**
   ```bash
   python -m cProfile -s cumtime script.py | head -40   # where time goes
   pyinstrument script.py                                # readable call tree
   py-spy top --pid 1234                                 # a live process, no restart
   python -X importtime script.py                        # slow startup
   ```
   Read `cumtime` (time including callees) to find the responsible subsystem,
   `tottime` (time in the function itself) to find the hot function.
4. **Fix the largest cost only.** Amdahl's law: making a function that is 3% of
   runtime twice as fast buys you 1.5%. Ignore it.
5. **Re-measure.** If it did not move the number, revert it — you have added
   complexity for nothing, and the next reader will assume it was necessary.
6. **Leave the evidence.** A comment with the before/after number is what stops
   someone "simplifying" your optimisation back out next quarter.

The two biggest real-world Python wins are almost never CPU micro-optimisation:
they are **an accidentally quadratic algorithm** and **N+1 I/O**. Look for those
first — a profiler that samples CPU will not show you time spent waiting on a
database.

## Cost of built-in operations

Average-case complexity, and the constant factors that matter in practice.

| Operation | list | deque | set / dict |
|---|---|---|---|
| index `x[i]` | O(1) | O(n) | — |
| append / add | O(1) amortised | O(1) | O(1) |
| insert or pop at front | **O(n)** | O(1) | — |
| `x in c` | **O(n)** | O(n) | **O(1)** |
| delete by value | O(n) | O(n) | O(1) |

Other costs worth knowing:

- `list.sort()` / `sorted()` — O(n log n), C-implemented, and very fast. Sorting
  and then scanning often beats a clever manual approach.
- `str` is immutable: `s += x` in a loop is O(n²) because every step copies the
  whole string. `"".join(parts)` is O(n).
- `list.pop(0)` is O(n) — use `collections.deque` for a queue.
- Slicing copies: `big[:-1]` allocates a new list of n-1 items. In a loop that
  is quadratic.
- `x in some_list` inside a loop over another list is the classic accidental
  O(n²). Build a `set` once outside the loop.
- `dict` preserves insertion order (guaranteed since 3.7) and is highly
  optimised — reach for it before inventing anything.

## Choosing the data structure

| Situation | Use | Not |
|---|---|---|
| Membership tests | `set` | `list` |
| Lookup by key | `dict` | list of tuples scanned |
| Queue / sliding window | `collections.deque` | `list` with `pop(0)` |
| Counting occurrences | `collections.Counter` | manual `dict` increments |
| Grouping | `collections.defaultdict(list)` | `if k not in d: d[k] = []` |
| Top-k of many | `heapq.nlargest` | full `sorted()` then slice |
| Sorted inserts / range queries | `bisect` on a sorted list | re-sorting each insert |
| Many small fixed-shape objects | `dataclass(slots=True)` / `NamedTuple` | `dict` per object |
| Large arrays of numbers | `numpy` / `array` | `list` of floats |
| Fixed set of flags | `frozenset` / `enum.Flag` | list of strings |

```py
# 60s → 0.4s: the only change is building a set once.
banned = set(banned_ids)                      # O(n) once
flagged = [u for u in users if u.id in banned]  # O(1) per user
```

## Doing less work

**Hoist loop invariants.** Anything whose value does not change per iteration
belongs above the loop — a compiled regex, a config lookup, `len()` of something
static, an attribute chain.

```py
# Before: re-compiles the pattern and re-reads the attribute chain n times.
for line in lines:
    if re.match(r"^\d{4}-\d{2}-\d{2}", line) and line[:4] == str(cfg.filters.year):
        ...

# After
date_re = re.compile(r"^\d{4}-\d{2}-\d{2}")
year = str(cfg.filters.year)
for line in lines:
    if date_re.match(line) and line[:4] == year:
        ...
```

**Short-circuit early.** Order `and`/`or` operands so the cheapest, most
selective test runs first. Return as soon as the answer is known.

**Do the filtering in the database, not in Python.** `WHERE`, `LIMIT`, and
aggregate functions in SQL move the work to a system designed for it and cut the
bytes crossing the wire. Fetching 1M rows to count them in Python is the most
expensive way to run `SELECT count(*)`.

**Kill N+1 patterns.** One query in a loop over 500 parents is 501 round trips.
Fetch the children in one query keyed by parent id and group in memory, or use
the ORM's eager-loading (`selectinload`/`joinedload` in SQLAlchemy,
`select_related`/`prefetch_related` in Django). The same rule applies to HTTP
calls and file reads.

## Caching

```py
from functools import cache, lru_cache

@cache                              # unbounded; only for a small key space
def parse_rule(text: str) -> Rule: ...

@lru_cache(maxsize=1024)            # bounded; safe for user-supplied keys
def geocode(address: str) -> LatLng: ...
```

Rules that prevent the usual bugs:

- Only cache **pure** functions. Caching something that reads a file or a
  database returns stale data forever, and the bug appears hours later.
- Arguments must be hashable, so no lists or dicts — convert to tuples/frozensets
  at the call site.
- `@cache` on a method keeps `self` alive for the process lifetime: a memory
  leak that looks like a mystery. Cache module-level functions, or use
  `functools.cached_property` for per-instance memoisation.
- Unbounded caches keyed on user input are a memory-exhaustion vector. Use
  `lru_cache(maxsize=...)`.
- For anything cross-process or with a TTL, use a real cache (Redis, disk) with
  an explicit invalidation story — see `perf-engineering`.

## Streaming and memory

```py
# Loads the whole file into memory — dies on a 4GB log.
lines = open(path).readlines()
total = sum(int(l.split(",")[3]) for l in lines)

# Flat memory regardless of file size.
with open(path) as f:
    total = sum(int(line.split(",", 4)[3]) for line in f)
```

- A generator expression passed straight to `sum`/`any`/`max`/`join` never
  builds the intermediate list. Wrapping it in `[...]` does.
- `itertools.islice`, `chain`, `groupby`, `batched` (3.12+) compose streams
  without materialising them.
- Reading a large CSV: `pandas.read_csv(..., chunksize=)`, or `polars.scan_csv`
  which is lazy and streams by design.
- `sys.getsizeof` for one object, `tracemalloc` for allocation sources, `memray`
  for a full memory profile with a flame graph.
- `__slots__` (or `@dataclass(slots=True)`) removes the per-instance `__dict__`
  — a large saving when you hold millions of small objects, and it also makes
  attribute access faster.
- Deleting a name does not free memory if something else still references it.
  Circular references are collected eventually but not immediately; break cycles
  explicitly in long-lived structures, or use `weakref`.

## Vectorising with numpy and polars

For numeric work over many rows, the interpreter loop is the entire cost. Moving
it into C is not a micro-optimisation — it is typically a 10-100x change.

```py
# Python loop: one interpreter step per element.
result = [x * 2 + 1 for x in values]

# numpy: one C loop over a contiguous buffer.
result = values * 2 + 1          # values is an ndarray
```

- Never loop over a numpy array in Python (`for i in range(len(arr))`). If you
  are indexing element by element, you have given up the entire benefit.
- Use boolean masks (`arr[arr > 0]`) rather than filtering in Python.
- Watch dtypes: an accidental `object` dtype makes a numpy array slower than a
  list. Check with `arr.dtype`.
- pandas: `df.iterrows()` is extremely slow — use vectorised column operations,
  `groupby().agg()`, or `df.to_numpy()` for a tight numeric loop. `df.apply` is
  a loop with extra steps; it is a fallback, not a solution.
- polars is faster than pandas for most operations and its lazy API
  (`scan_parquet(...).filter(...).collect()`) does predicate pushdown so it
  reads less from disk. Prefer it for new pipelines over large data.
- For a genuinely serial numeric algorithm that cannot vectorise, `numba`'s
  `@njit` compiles it; that is the point where a C extension becomes worth
  considering.

## Micro-optimisations that are real

Only after the above, and only in a measured hot loop:

- **Bind lookups to locals.** Local variable access is faster than a global or an
  attribute chain, and in a million-iteration loop that shows up:
  `append = out.append` outside the loop, then `append(x)` inside.
- **Avoid function calls in the innermost loop** — Python call overhead is
  significant. Inlining a two-line helper into a hot loop is one of the few
  places where duplicating code is justified; comment why.
- **`try/except` is nearly free when nothing raises** but expensive when it does.
  Exceptions for the common case in a hot loop is a real cost.
- **`str.translate` / `bytes.translate`** beats chained `.replace()` calls.
- **`operator.itemgetter`/`attrgetter`** as a sort key is C-implemented and
  faster than a lambda.
- **Prefer `%` or `.format()`-free logging placeholders** so disabled log levels
  cost nothing.

What is *not* worth doing: rewriting comprehensions as `map`/`filter` for speed
(the difference is noise and readability drops), avoiding f-strings, and
"optimising" anything that runs once.

## Concurrency and the GIL

The GIL means only one thread executes Python bytecode at a time in the standard
build. It is released during I/O and inside most C extension calls (numpy,
compression, hashing).

- **I/O-bound** (HTTP, database, disk): threads or `asyncio` give near-linear
  speedup. Prefer `asyncio` for thousands of concurrent waits, threads when the
  library is blocking and you cannot change it (`asyncio.to_thread`).
- **CPU-bound pure Python**: threads give you nothing. Use
  `ProcessPoolExecutor`, and be aware every argument and result is pickled and
  copied — for large data that overhead can exceed the gain. Batch the work per
  process.
- **CPU-bound numeric**: numpy/polars release the GIL internally, so threads do
  help; this is usually better than processes because there is no copying.
- **Free-threaded builds** (`python3.14t`) are officially supported from 3.14 and
  do run threads in parallel for pure Python. Cost: roughly 10% slower
  single-threaded and 15-20% more memory, plus your C dependencies must support
  it. Choose it deliberately for parallel CPU workloads, not by default.

Always bound concurrency (`asyncio.Semaphore`, a pool size) — unbounded fan-out
at a database or an API is a self-inflicted outage.

## Benchmarking honestly

```py
import timeit
timeit.timeit("'-'.join(map(str, range(100)))", number=100_000)
```

- Warm up first; the first run includes import and cache-population costs.
- Run repeatedly and report the **minimum** for micro-benchmarks (noise only
  adds time) but the **distribution** (p50/p95) for anything involving I/O,
  where the tail is what users feel.
- Benchmark on data the size and shape of production. Sorted input, all-unique
  keys, and tiny n each hide different problems.
- Change one thing at a time, and re-run the baseline in the same session —
  machine state drifts.
- `pytest-benchmark` for tracking a benchmark in CI; `hyperfine` for whole-CLI
  timing.
- Beware measuring a cached result: an LRU cache or an OS page cache makes the
  second run fast for reasons unrelated to your change.
