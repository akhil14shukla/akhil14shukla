# Errors, logging, concurrency, and entry points

Read this when adding error handling, wiring logging, choosing a concurrency
model, or writing the entry point of a script or service.

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
