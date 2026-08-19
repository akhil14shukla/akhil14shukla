# Python idioms: before and after

Read this when you are unsure of the idiomatic form, or rewriting code that
works but reads clumsily.

Each rewrite below is one a reviewer would ask for. The "after" is not shorter
for its own sake — it is either clearer, safer, or measurably faster, and the
note says which.

## The idioms that carry their weight

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

---

## Mutable default argument

```py
def add_tag(tag: str, tags: list[str] = []) -> list[str]:   # BUG
    tags.append(tag); return tags
# The list is created once, at definition time, and shared by every call.

def add_tag(tag: str, tags: list[str] | None = None) -> list[str]:
    tags = [] if tags is None else tags
    tags.append(tag); return tags
```

## Building a string in a loop

```py
html = ""
for row in rows: html += f"<tr>{row}</tr>"        # O(n²): each += copies

html = "".join(f"<tr>{row}</tr>" for row in rows)  # O(n)
```

## Indexing with range(len(...))

```py
for i in range(len(items)):
    print(i, items[i])

for i, item in enumerate(items):
    print(i, item)
```

## Parallel lists

```py
for i in range(len(names)):
    print(names[i], scores[i])          # silently truncates if lengths differ

for name, score in zip(names, scores, strict=True):
    print(name, score)                  # raises if lengths differ — the bug is visible
```

## Checking membership against a list

```py
blocked = ["a@x.com", "b@x.com", ...]     # 10k entries
if email in blocked: ...                  # O(n) scan on every call

blocked = frozenset(BLOCKED_EMAILS)       # build once
if email in blocked: ...                  # O(1)
```

## Manual counting and grouping

```py
counts = {}
for w in words:
    if w in counts: counts[w] += 1
    else: counts[w] = 1

from collections import Counter
counts = Counter(words)                   # C-implemented, and .most_common() is free
```

```py
by_user = {}
for e in events:
    by_user.setdefault(e.user_id, []).append(e)

from collections import defaultdict
by_user = defaultdict(list)
for e in events: by_user[e.user_id].append(e)
```

## Filtering then transforming

```py
out = []
for u in users:
    if u.is_active:
        out.append(u.email.lower())

out = [u.email.lower() for u in users if u.is_active]
```

But stop before it becomes unreadable — a comprehension with two `for` clauses,
an `if`, and a ternary is worse than the loop:

```py
# Do not do this.
rows = [transform(c) if c.ok else fallback(c) for p in parents for c in p.children if c.visible]
```

## Bare except

```py
try:
    value = int(raw)
except:                       # also catches KeyboardInterrupt and your own typos
    value = 0

try:
    value = int(raw)
except ValueError:            # exactly what can go wrong here
    value = 0
```

## Losing the cause

```py
except KeyError as exc:
    raise ConfigError("missing key")           # traceback to the real cause is gone

except KeyError as exc:
    raise ConfigError(f"missing key: {exc}") from exc
```

## Manual file handling

```py
f = open(path)
data = f.read()
f.close()                     # never runs if read() raises

with open(path) as f:
    data = f.read()

# Better still for a whole small file:
data = Path(path).read_text(encoding="utf-8")
```

Always pass `encoding="utf-8"` explicitly — the platform default differs between
machines and has produced a long tail of "works on my laptop" bugs.

## os.path

```py
import os
full = os.path.join(os.path.dirname(__file__), "data", "cfg.json")
if os.path.exists(full): ...

from pathlib import Path
full = Path(__file__).parent / "data" / "cfg.json"
if full.exists(): ...
```

## Type checks

```py
if type(x) == list: ...            # fails for subclasses
if isinstance(x, list): ...        # correct
if isinstance(x, Sequence): ...    # usually what you actually meant
```

## Comparing to None / True

```py
if x == None: ...       if flag == True: ...
if x is None: ...       if flag: ...
```

## Dict iteration

```py
for k in d.keys(): ...          # the .keys() is redundant
for k in d: ...

for k in d: v = d[k]            # a second lookup per key
for k, v in d.items(): ...
```

## Nested conditionals for one value

```py
if user is not None:
    if user.profile is not None:
        name = user.profile.name
    else:
        name = "anon"
else:
    name = "anon"

name = user.profile.name if user and user.profile else "anon"
```

## Reading a whole file to process line by line

```py
for line in open(path).readlines(): ...   # entire file in memory, handle leaked

with open(path, encoding="utf-8") as f:
    for line in f: ...                    # streams, closes deterministically
```

## Returning multiple unnamed values

```py
def stats(xs): return min(xs), max(xs), sum(xs) / len(xs)
lo, hi, avg = stats(xs)     # fine for 2-3 at one call site

class Stats(NamedTuple):    # better once it travels or grows
    low: float
    high: float
    mean: float
```

## Flag parameters

```py
def export(data, as_csv=False, compress=False, include_header=True): ...
export(rows, True, False, True)     # unreadable

def export(data, *, fmt: Literal["csv", "json"], compress: bool = False): ...
export(rows, fmt="csv", compress=False)
```

## Stdlib modules people reimplement by hand

| Instead of writing | Use |
|---|---|
| Manual counting / grouping / rotating buffers | `collections` (`Counter`, `defaultdict`, `deque`) |
| Nested loops over combinations, chunking, running totals | `itertools` (`product`, `combinations`, `batched`, `accumulate`, `groupby`) |
| Custom memoisation dict | `functools.cache`, `lru_cache`, `cached_property` |
| Path string manipulation | `pathlib` |
| Hand-rolled CLI arg parsing | `argparse` |
| Date parsing with `strptime` on ISO strings | `datetime.fromisoformat` |
| Hand-written retry loop with sleeps | `tenacity` (or a small explicit backoff helper) |
| Float money arithmetic | `decimal.Decimal` or integer cents |
| Random tokens/passwords with `random` | `secrets` — `random` is not cryptographically secure |
| Temp files with manual cleanup | `tempfile.TemporaryDirectory` |
| Comparing/merging dicts and objects deeply | `dataclasses.replace`, `copy.deepcopy`, `operator` |
| Custom CSV parsing with `split(",")` | `csv` — quoting and embedded newlines will break your split |

## Timezone-naive datetimes

```py
now = datetime.now()                    # naive: ambiguous, compares wrongly
now = datetime.now(tz=UTC)              # aware, unambiguous
```

Store and compute in UTC; convert to local time only for display. Comparing a
naive and an aware datetime raises at runtime, usually in production.
