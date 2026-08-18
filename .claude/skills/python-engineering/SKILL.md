---
name: python-engineering
description: Write Python that is fast, typed, and obvious to a reader who has never seen the codebase — project setup with uv/ruff/pyproject, type annotations, data modelling, stdlib-first idioms, CPython performance, error handling, logging, and concurrency choices. Use this for ANY task where Python source is created or changed: new scripts and CLIs, packages and libraries, APIs, data pipelines, notebooks being turned into real code, refactors, bug fixes, and performance work. Trigger on "write a Python script", "build a Python package/CLI/API", "refactor this Python", "make this Python faster", "add type hints", "clean up this .py file", or any mention of pandas, numpy, FastAPI, Django, Flask, pytest, asyncio, or a .py path.
---

# Python engineering

Python lets you write a working prototype in twenty minutes and a maintenance
problem in twenty-one. The difference is almost entirely a set of decisions made
at write time, and they are all cheap if made then and expensive later.

Two ideas run through everything below:

- **The reader is a stranger.** Types, names, and small pure functions are how a
  file explains itself to someone with no context. Python will happily let you
  pass anything anywhere; annotations are how you tell the next person — and the
  type checker — what you actually meant.
- **Fast Python is Python that does less work in the interpreter.** The
  interpreter is the slow part. Speed comes from choosing the right data
  structure, letting C-implemented built-ins do the looping, and not doing work
  twice — never from clever one-liners. See the performance section; it is the
  part most people get wrong by guessing.

`code-craft` holds the language-agnostic craft (naming, function shape, error
taxonomy, when to restructure). Everything here is what **Python specifically**
rewards or punishes. If you only load one, the universal non-negotiables are:
name things for what they are, keep functions to one job, never swallow an
error, comment *why* not *what*, and validate at the boundary.

## Project setup

Before writing code in a new project, get this in place — it takes two minutes
and prevents the whole class of "works on my machine" problems.

```bash
uv init --lib my-project        # or --app for a CLI/service
cd my-project
uv add --dev pytest ruff mypy
```

`uv` is the current standard for environments, dependency resolution, locking,
and running (it replaces pip + venv + pip-tools + pyenv, and is fast enough that
lockfiles stop being a chore). `uv sync` reproduces the environment exactly from
`uv.lock`, which is committed.

Use the **src layout** and put every tool's configuration in `pyproject.toml`:

```
my-project/
├── pyproject.toml          # deps, build config, and all tool settings
├── uv.lock                 # committed
├── README.md
├── src/my_project/
│   ├── __init__.py
│   └── ...
└── tests/
```

src layout matters for a concrete reason, not aesthetics: without it, `python`
run from the project root imports your source directory directly, so your tests
exercise a copy that is not the installed package. Packaging bugs — a missing
`__init__.py`, a data file not included, a module that only imports because the
CWD happened to be right — then ship to users undetected.

Minimum `pyproject.toml` tool config:

```toml
[project]
requires-python = ">=3.12"

[tool.ruff]
line-length = 100
[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "RUF", "N", "C4", "PTH", "ARG", "TRY"]
# E/F pycodestyle+pyflakes, I import sort, UP pyupgrade, B bugbear (real bugs),
# SIM simplification, N naming, C4 comprehensions, PTH pathlib, TRY exceptions.

[tool.mypy]
strict = true
[tool.pytest.ini_options]
addopts = "-q --strict-markers"
```

Then `ruff format` (formatting), `ruff check --fix` (lint), `mypy src`
(types), `pytest` (tests). Run all four before you call anything done.

**Target 3.12+** for new work unless something pins you lower; 3.10 reaches
end of life in October 2026. Say which version you targeted and why if you
choose otherwise.

## Types

Annotate every function that anyone else calls — parameters and return. Inside a
function, annotate only where the type is not obvious from the assignment.
Annotations are not decoration: they let `mypy` catch a whole class of bug
before runtime, and they tell the reader the contract without them reading the
body.

```py
def summarise_orders(
    orders: Sequence[Order],
    *,
    since: datetime | None = None,
    currency: Currency = Currency.USD,
) -> OrderSummary:
```

Modern syntax (3.10+), which the `UP` ruff rules will enforce:

- `str | None`, not `Optional[str]`; `int | str`, not `Union[int, str]`
- `list[str]`, `dict[str, int]`, `tuple[int, ...]` — not the `typing` versions
- `Self` for fluent/factory returns, `Literal["a", "b"]` for closed string sets,
  `Final` for module constants
- **Accept the general, return the concrete**: take `Iterable[T]`/`Sequence[T]`/
  `Mapping[K, V]`, return `list[T]`/`dict[K, V]`. Callers can then pass whatever
  they have, while your return type stays useful.
- `Protocol` for structural interfaces — it lets you type a dependency without
  the caller inheriting from anything, which is what makes test doubles easy.
- `TypedDict` for JSON-ish dicts you cannot turn into classes; `NewType` for IDs
  (`UserId = NewType("UserId", int)`) so a user id cannot be passed as an order id.

`Any` disables checking for everything downstream of it. If you genuinely need
it, leave a comment saying why. `cast()` is a claim you are making to the type
checker with no runtime check behind it — reserve it for cases you can justify.

Deeper material — generics, variance, overloads, narrowing, typing decorators
and `**kwargs`, and how to add types to an untyped codebase — is in
`references/typing-and-data.md`.

## Data modelling

Passing dicts around is the most common source of unreadable Python. A dict has
no contract: nobody can tell what keys exist, nothing catches a typo, and the
IDE cannot help.

```py
# Before: what's in it? who knows. `order["totl"]` fails at runtime, in prod.
def process(order: dict) -> dict: ...

# After: the shape is the documentation, and typos are caught by mypy.
@dataclass(frozen=True, slots=True)
class Order:
    id: OrderId
    customer_id: CustomerId
    lines: tuple[OrderLine, ...]
    placed_at: datetime

    @property
    def total_cents(self) -> int:
        return sum(line.total_cents for line in self.lines)
```

Choosing the right container:

| Need | Use |
|---|---|
| Value object, compared by fields, immutable | `@dataclass(frozen=True, slots=True)` |
| Same, but must be hashable and tuple-like | `NamedTuple` |
| Closed set of named values | `enum.Enum` / `StrEnum` / `IntEnum` |
| Validating untrusted external input | `pydantic.BaseModel` — at the boundary only |
| Genuinely dynamic keys (counts, caches, JSON passthrough) | `dict` |

`frozen=True` makes accidental mutation an error and the object hashable;
`slots=True` cuts memory per instance substantially and speeds attribute access
(worth it whenever you create many instances). Use pydantic where data arrives
from outside — HTTP bodies, config files, message payloads — and convert to your
own types inward, so validation cost and framework coupling stay at the edge.

## Idioms that carry their weight

These are the ones that change how the code reads, not trivia.

- **Comprehensions for transformation; a loop when there is a side effect.**
  A comprehension with an `if` and a nested `for` and a ternary is worse than
  the loop it replaced. One `for`, optionally one `if` — past that, write the
  loop.
- **Generators for anything you stream.** `yield` keeps memory flat over a
  100M-row file and lets the caller stop early. Returning a list forces the
  whole thing into memory whether or not the caller needs it.
- **`pathlib`, not `os.path`.** `path.read_text()`, `path / "sub" / "file.txt"`,
  `path.exists()` — shorter, cross-platform, and typed.
- **Context managers for every resource**, and `contextlib.contextmanager` when
  you need your own. If you write `f = open(...)` without `with`, the file stays
  open until GC on any error path.
- **Unpack instead of indexing**: `for i, item in enumerate(xs)`,
  `for a, b in zip(xs, ys, strict=True)`. `strict=True` (3.10+) catches the
  silently-truncated-zip bug, which is otherwise invisible.
- **EAFP over LBYL** where a race is possible: `try: f = open(p)` beats
  `if p.exists(): open(p)`, because the file can vanish between the two lines.
- **`match` for dispatching on shape**, not as a switch replacement — its value
  is destructuring (`case {"type": "order", "id": int(id)}`).
- **f-strings everywhere except logging** (see below), and `f"{value!r}"` in
  error messages so you can see quoting and whitespace.
- **`dict.get(k, default)` / `collections.defaultdict` / `dict.setdefault`**
  instead of `if k in d: ... else: ...`.
- **Keyword-only arguments** for anything a caller could get in the wrong order:
  put `*` in the signature. `resize(img, 100, 200)` is a coin flip;
  `resize(img, width=100, height=200)` is not.

The mistakes worth naming explicitly, because they are silent:

- **Mutable default arguments.** `def f(items=[])` shares one list across every
  call, forever. Use `None` and create inside.
- **`except:` or `except Exception:` around a whole block.** It catches your own
  typos and turns them into wrong answers.
- **Mutating a list while iterating over it** — iterate over a copy or build a
  new list.
- **`==` on floats.** Use `math.isclose`, or integers/`Decimal` for money.
- **`from module import *`** — the reader cannot tell where a name came from.
- **Module-level side effects** (opening connections, reading env, mutating
  globals at import). Import order becomes significant and tests break.
- **`assert` for validation.** `python -O` removes asserts. Use them for
  invariants in tests and internal sanity checks only; raise real exceptions for
  input validation.

A fuller before/after catalogue is in `references/idioms.md`.

## Performance: the model that is actually true

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

## Errors

```py
class BillingError(Exception):
    """Base for everything this module raises, so callers can catch the family."""

class CardDeclined(BillingError):
    def __init__(self, order_id: OrderId, reason: str) -> None:
        super().__init__(f"card declined for order {order_id}: {reason}")
        self.order_id = order_id
        self.reason = reason          # data as fields, not parsed from the string
```

- Catch the narrowest exception that you can actually handle, close to where it
  happens. `except Exception` at the top of a request handler to return a 500 is
  fine; `except Exception` around three lines to "be safe" is a bug generator.
- **Always chain**: `raise ProcessingError(f"row {n}") from exc`. Losing the
  original traceback removes the only evidence of the real cause.
- Do not use exceptions for ordinary flow in hot paths — `dict.get` beats
  `try/except KeyError` when misses are common.
- `finally` or a context manager for cleanup, so the error path releases the
  same resources the happy path does.

## Logging

```py
logger = logging.getLogger(__name__)      # module level, once, by __name__

logger.info("charged order %s for %d cents", order_id, amount_cents)
```

`print` in library or application code is not observable in production. Use
`%s` placeholders rather than f-strings in log calls so the formatting cost is
skipped when the level is disabled, and so log aggregators can group by message
template. Configure handlers once, in the entry point — never in a library
module. Never log secrets, tokens, or personal data. `logger.exception(...)`
inside an `except` block includes the traceback automatically.

## Concurrency: pick by what is blocking

| Workload | Use | Why |
|---|---|---|
| Waiting on network/disk (most web, API, scraping work) | `asyncio`, or threads | The wait releases the GIL; concurrency is nearly free |
| Many blocking library calls you cannot make async | `ThreadPoolExecutor` | Threads are fine when the work is I/O-bound |
| CPU-bound pure Python (parsing, simulation, image work) | `ProcessPoolExecutor` | Separate interpreters sidestep the GIL |
| CPU-bound numeric work | numpy/polars/numba | Releases the GIL inside C, and is faster anyway |

The GIL means threads do not speed up CPU-bound *Python* code in the standard
build. Python 3.14 makes the free-threaded build (`python3.14t`) officially
supported, which does allow real thread parallelism, at roughly a 10%
single-threaded penalty and higher memory use — worth it for genuinely parallel
CPU work, not a default.

Async rules that prevent the usual disasters: never call a blocking function
inside a coroutine (it stalls the whole event loop — use `asyncio.to_thread`);
give every await that touches the network a timeout; bound concurrency with a
`Semaphore` rather than firing 10,000 tasks at a database; and do not mix
`asyncio.run` with an already-running loop.

## Scripts and entry points

Even a one-off script deserves a shape someone can reuse:

```py
def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    ...
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

Keeping `main()` importable and returning an exit code makes the script
testable, and `if __name__` guards mean importing it does not execute it.
Use `argparse` for real CLIs (or `typer`/`click` when the surface is large),
never `sys.argv` indexing.

## Testing

`pytest`, `tests/` mirroring `src/`, one behaviour per test, no logic inside
tests. The Python-specific tools worth knowing: `@pytest.mark.parametrize` for
table-driven cases, `tmp_path` for real files, `monkeypatch` for environment and
attributes, fixtures for shared setup (function-scoped by default — a
session-scoped mutable fixture creates order dependence between tests), and
`pytest.raises(Error, match="...")` to assert failures actually fail the right
way. `testing-craft` covers what makes a test worth its maintenance cost.

## Before you call it done

```bash
ruff format . && ruff check --fix . && mypy src && pytest
```

All four clean. Then re-read the diff: are the public functions annotated, is
every resource in a `with`, does every `except` name a specific type and chain
its cause, and would someone who has never seen this file know what it does from
the names alone?

## References

- `references/performance.md` — complexity tables, profiling workflow,
  vectorisation, caching, memory, free-threading. Read before optimising.
- `references/typing-and-data.md` — generics, protocols, overloads, narrowing,
  pydantic vs dataclasses, typing an untyped codebase.
- `references/idioms.md` — before/after catalogue of Python-specific rewrites,
  including the stdlib module you probably forgot exists.
