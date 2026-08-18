---
name: python-engineering
description: Write Python that is fast, typed, and obvious to a stranger — setup, typing, data modelling, stdlib idioms, CPython performance, errors, logging, concurrency. Use for ANY task where Python source is created or changed: scripts, CLIs, packages, APIs, data pipelines, refactors, bug fixes, performance work. Trigger on "write a Python script", "build a Python package/CLI/API", "refactor this Python", "make this faster", "add type hints", a .py path, or any mention of pandas, numpy, FastAPI, Django, Flask, pytest, or asyncio.
---

# Python engineering

Python lets you write a working prototype in twenty minutes and a maintenance
problem in twenty-one. The difference is a handful of decisions made at write
time, all cheap then and expensive later.

Two ideas govern the rest: **the reader is a stranger**, so types, names, and
small pure functions are how a file explains itself; and **fast Python is Python
that does less work in the interpreter**, so speed comes from the right data
structure and letting C-implemented built-ins do the looping, never from clever
one-liners.

## The standing rules

These apply to every Python file you touch. The detail behind each one is in the
references below — read the one that matches what you are actually doing.

1. **Annotate every function anyone else calls** — parameters and return. Modern
   syntax: `str | None`, `list[str]`, `Self`, `Literal`. Accept the general
   (`Iterable`, `Sequence`, `Mapping`), return the concrete (`list`, `dict`).
   `Any` disables checking for everything downstream; if you need it, say why.
2. **Model data as types, not dicts.** `@dataclass(frozen=True, slots=True)` for
   internal values; pydantic only at the boundary where untrusted data arrives.
   A dict passed between three functions is an undocumented type, and a typo in
   a key fails in production rather than in the checker.
3. **Every resource in a `with`**, and `encoding="utf-8"` stated explicitly —
   the platform default differs between machines. `pathlib`, not `os.path`.
4. **Catch the narrowest exception you can actually handle, and always chain**:
   `raise ProcessingError(f"row {n}") from exc`. A bare `except:` catches your
   own typos and turns a loud bug into a silent wrong answer.
5. **`logger = logging.getLogger(__name__)` at module level**, `%s` placeholders
   rather than f-strings so disabled levels cost nothing. Never `print` in
   library or application code, and never log secrets or personal data.
6. **No mutable default arguments.** `def f(xs=[])` shares one list across every
   call, forever. Use `None` and create inside.
7. **Comprehension to transform, loop when there is a side effect, generator to
   stream.** One `for` and optionally one `if` — past that, write the loop.
8. **Speed comes from doing less work, not from clever code**: the right data
   structure, C-level built-ins, and batched I/O. Never guess — profile first,
   and leave the measured number in a comment when you optimise.
9. **Keep `main()` importable and returning an exit code**, guarded by
   `if __name__ == "__main__": raise SystemExit(main())`, so the script is
   testable and importing it does not run it.

**Target 3.12+** for new work unless something pins you lower; 3.10 reaches end
of life in October 2026. Say so if you choose otherwise.

## Before you call it done

```bash
ruff format . && ruff check --fix . && mypy src && pytest
```

All four clean. Then re-read the diff: public functions annotated, every
resource in a `with`, every `except` narrow and chained, and names a stranger
would understand without opening anything else.

## Read the reference that matches your task

Do not read these speculatively — each is written to be loaded at the moment the
question comes up.

| If you are… | Read |
|---|---|
| Starting a project, or one has no lockfile, tool config, or `src/` layout | `references/setup.md` |
| Designing types, generics, protocols, overloads, or choosing dataclass vs pydantic | `references/typing-and-data.md` |
| Unsure of the idiomatic form, or rewriting clunky code | `references/idioms.md` |
| Working on speed, memory, profiling, vectorising, or the GIL | `references/performance.md` |
| Writing error handling, logging, concurrency, or an entry point | `references/runtime.md` |

Adjacent skills, when the task moves past Python itself: `repo-architect` for
where files go, `testing-craft` for what the tests should assert,
`perf-engineering` for the language-agnostic optimisation method, `docs-craft`
for the README and docstrings, `ship-quality` for the pre-commit gate.
