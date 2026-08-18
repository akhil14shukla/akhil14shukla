# Python idioms: before and after

Each rewrite below is one a reviewer would ask for. The "after" is not shorter
for its own sake — it is either clearer, safer, or measurably faster, and the
note says which.

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
