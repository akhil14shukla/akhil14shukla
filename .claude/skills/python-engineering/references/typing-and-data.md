# Typing and data modelling in Python

## Contents

- [Annotating: the standing rules](#annotating-the-standing-rules)
- [Choosing a container](#choosing-a-container)
- [What to annotate](#what-to-annotate)
- [Protocols: interfaces without inheritance](#protocols-interfaces-without-inheritance)
- [Generics](#generics)
- [Narrowing and guards](#narrowing-and-guards)
- [Overloads](#overloads)
- [Typing callables, decorators, and kwargs](#typing-callables-decorators-and-kwargs)
- [dataclasses vs pydantic vs attrs](#dataclasses-vs-pydantic-vs-attrs)
- [Adding types to an untyped codebase](#adding-types-to-an-untyped-codebase)

## Annotating: the standing rules

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

## Choosing a container

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

---

## What to annotate

Annotate every parameter and return of anything importable. Inside a function
body, annotate only where inference fails or the type is genuinely unclear
(an empty collection: `seen: set[UserId] = set()`).

**Accept general, return concrete.** A parameter typed `Iterable[str]` accepts a
list, a generator, a tuple, and a file object. A return typed `list[str]` tells
the caller they can index and re-iterate it.

```py
def normalise(names: Iterable[str]) -> list[str]:
    return [n.strip().lower() for n in names]
```

Mutability is part of the contract: `Sequence[T]` and `Mapping[K, V]` promise you
will not mutate the argument; `list[T]`/`dict[K, V]` as a parameter type says you
might. Choose deliberately.

**`NewType` for identifiers.** Any codebase with more than one kind of id
eventually passes the wrong one:

```py
UserId  = NewType("UserId", int)
OrderId = NewType("OrderId", int)

def load_order(order_id: OrderId) -> Order: ...
load_order(user.id)     # mypy error — costs nothing at runtime
```

**`Final` and `Literal`** for constants and closed sets:

```py
MAX_RETRIES: Final = 3
def open_file(path: Path, mode: Literal["r", "w", "a"]) -> IO[str]: ...
```

## Protocols: interfaces without inheritance

A `Protocol` types a *shape*. The implementer does not import or subclass
anything, which means you can type third-party objects and write test doubles
that are just small classes.

```py
class Clock(Protocol):
    def now(self) -> datetime: ...

class SystemClock:
    def now(self) -> datetime: return datetime.now(UTC)

@dataclass
class FrozenClock:                 # a complete test double, no mocking library
    at: datetime
    def now(self) -> datetime: return self.at

def is_expired(token: Token, clock: Clock) -> bool:
    return token.expires_at < clock.now()
```

This is the single most useful typing feature for testability: injecting a
`Clock`, a `Storage`, or an `HttpClient` protocol removes the need to patch
globals in tests.

Use `@runtime_checkable` only if you need `isinstance` against it — it checks
method *names* only, not signatures, so it is a weak check.

## Generics

Modern syntax (3.12+) needs no `TypeVar` declaration:

```py
def first[T](items: Sequence[T]) -> T | None:
    return items[0] if items else None

class Repository[T]:
    def get(self, id: str) -> T | None: ...
    def save(self, item: T) -> None: ...
```

Pre-3.12 this is `T = TypeVar("T")` plus `Generic[T]`. Constrain when it
matters: `def total[T: (int, float)](xs: Sequence[T]) -> T`.

Reach for generics when a container or function genuinely works for any type. If
it works for two known types, an overload or a union is clearer.

## Narrowing and guards

mypy tracks narrowing through `isinstance`, `is None`, truthiness, and
`assert`:

```py
def describe(value: int | str | None) -> str:
    if value is None:
        return "nothing"
    if isinstance(value, int):
        return f"number {value}"      # narrowed to int here
    return value.upper()              # narrowed to str here
```

For a custom check, `TypeIs` (3.13+; `TypeGuard` before that) teaches the
checker what your function proves:

```py
def is_str_list(v: list[object]) -> TypeIs[list[str]]:
    return all(isinstance(x, str) for x in v)
```

Exhaustiveness checking catches the case you forgot to add when an enum grows:

```py
def label(s: Status) -> str:
    match s:
        case Status.OPEN:   return "Open"
        case Status.CLOSED: return "Closed"
        case _ as unreachable:
            assert_never(unreachable)   # mypy errors here if a member is unhandled
```

## Overloads

When the return type depends on the arguments:

```py
@overload
def get(key: str) -> str | None: ...
@overload
def get(key: str, default: str) -> str: ...
def get(key: str, default: str | None = None) -> str | None:
    return _store.get(key, default)
```

Callers passing a default now get a non-optional type, so they do not have to
write a `None` check that can never fire.

## Typing callables, decorators, and kwargs

```py
Handler = Callable[[Request], Awaitable[Response]]

def with_retry[**P, R](fn: Callable[P, R]) -> Callable[P, R]:   # signature preserved
    @wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        ...
    return wrapper
```

`ParamSpec` (`**P`) is what keeps a decorator from erasing the wrapped
function's signature — without it, every call to a decorated function loses its
type checking. `Unpack[TypedDict]` types `**kwargs` precisely.

## dataclasses vs pydantic vs attrs

| | dataclass | pydantic | attrs |
|---|---|---|---|
| Runtime validation | none | yes, from the annotations | optional validators |
| Serialisation | manual / `asdict` | built in, JSON schema | `cattrs` |
| Cost per instance | lowest | highest | low |
| Dependency | stdlib | third-party | third-party |

**Use dataclasses for internal domain types.** They are stdlib, fast, and their
annotations are declarations, not runtime checks — which is what you want inside
your own code where the values are already validated.

**Use pydantic at the boundary** — request bodies, config files, message
payloads, third-party API responses. That is where validation earns its cost.
Convert to your own dataclasses inward so framework types do not spread through
the domain.

```py
@dataclass(frozen=True, slots=True, kw_only=True)
class Order:
    id: OrderId
    lines: tuple[OrderLine, ...] = ()          # immutable default; a list here
                                               # would need field(default_factory=list)
```

- `frozen=True` — hashable, safe to share, mutation is an error.
- `slots=True` — less memory, faster attributes.
- `kw_only=True` — call sites are self-documenting and adding a field never
  breaks positional callers.
- `field(default_factory=list)` for any mutable default; a bare `= []` is a
  `ValueError` in dataclasses (this is one place Python protects you).
- `__post_init__` for cross-field invariants, raising `ValueError` on violation.

## Adding types to an untyped codebase

Do it in this order — it converges instead of drowning you in errors:

1. Turn mypy on in non-strict mode over the whole package, with
   `ignore_missing_imports = true`. Fix nothing yet; see the size of it.
2. Annotate **leaf modules first** (pure functions, utilities, models). Types
   propagate upward, so leaves make everything above them cheaper.
3. Annotate public function signatures before internal ones — that is where the
   contract lives and where a wrong assumption costs most.
4. Enable strictness per module as it becomes clean:
   ```toml
   [[tool.mypy.overrides]]
   module = "my_project.domain.*"
   strict = true
   ```
5. Add `disallow_untyped_defs` last, once the count is small.

Never annotate by guessing. If you cannot tell what a function returns, read a
caller or write a test — a confidently wrong annotation is worse than none,
because everything downstream now trusts it.
