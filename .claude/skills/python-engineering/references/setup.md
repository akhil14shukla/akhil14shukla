# Setting up a Python project

Read this when starting a new project, or when an existing one has no lockfile,
no tool configuration, or a layout that lets tests import the source tree instead
of the installed package.

## The setup

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
