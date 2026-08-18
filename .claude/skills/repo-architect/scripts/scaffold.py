#!/usr/bin/env python3
"""Generate a correct starting repository tree.

Reconstructing a project skeleton from memory is where missing __init__.py
files, incomplete .gitignore entries, and inconsistent naming come from. This
writes a complete, consistent starting point instead.

    python scaffold.py --name my-project --lang python --kind app
    python scaffold.py --name my-svc --lang node --kind service --dry-run

Review what it produces and adapt it. It is a correct starting point, not a
finished project: you still choose a LICENSE, write the README body, and delete
anything the project does not need.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

LANGS = ("python", "node", "go", "rust")
KINDS = ("lib", "app", "cli", "service")

# --------------------------------------------------------------------------- #
# Shared files
# --------------------------------------------------------------------------- #

EDITORCONFIG = """\
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true
indent_style = space
indent_size = 4

[*.{js,jsx,ts,tsx,json,yml,yaml,md}]
indent_size = 2

[*.go]
indent_style = tab

[Makefile]
indent_style = tab
"""

GITIGNORE_COMMON = """\
# Environment and secrets — never commit real values
.env
.env.local
*.pem
*.key

# Editors and OS
.idea/
.vscode/
.DS_Store
Thumbs.db

# Logs and scratch
*.log
tmp/
.cache/
"""

GITIGNORE = {
    "python": """\
# Python
__pycache__/
*.py[cod]
.venv/
venv/
build/
dist/
*.egg-info/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
""",
    "node": """\
# Node
node_modules/
dist/
build/
coverage/
.next/
*.tsbuildinfo
.pnpm-store/
""",
    "go": """\
# Go
bin/
vendor/
*.test
*.out
""",
    "rust": """\
# Rust
target/
**/*.rs.bk
""",
}


def readme(name: str, lang: str, kind: str, run_cmd: str, test_cmd: str) -> str:
    return f"""\
# {name}

<!-- One sentence: what this does and who it is for. A reader decides in ten
     seconds whether this repository is relevant to them. -->

## Requirements

<!-- Language version, and any service (database, queue) needed to run it. -->

## Quick start

```bash
{run_cmd}
```

## Development

```bash
{test_cmd}
```

## Configuration

<!-- Every environment variable, what it does, and whether it is required.
     Keep this in sync with .env.example. -->

| Variable | Required | Default | Description |
|---|---|---|---|
|  |  |  |  |

## Project layout

<!-- One line per top-level directory, so a newcomer can navigate without
     opening files. -->

## License

<!-- Choose one and add a LICENSE file. Without it, nobody may legally use
     this code. -->
"""


CI = {
    "python": """\
name: CI
on: [push, pull_request]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
      - run: uv sync --all-extras --dev
      - run: uv run ruff format --check .
      - run: uv run ruff check .
      - run: uv run mypy src
      - run: uv run pytest --cov --cov-report=term-missing
""",
    "node": """\
name: CI
on: [push, pull_request]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - run: pnpm run lint
      - run: pnpm run typecheck
      - run: pnpm run test
""",
    "go": """\
name: CI
on: [push, pull_request]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: '1.23'
      - run: gofmt -l . | tee /dev/stderr | test -z "$(cat)"
      - run: go vet ./...
      - run: go test -race -cover ./...
""",
    "rust": """\
name: CI
on: [push, pull_request]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
        with:
          components: rustfmt, clippy
      - run: cargo fmt --check
      - run: cargo clippy --all-targets -- -D warnings
      - run: cargo test
""",
}

# --------------------------------------------------------------------------- #
# Per-language trees
# --------------------------------------------------------------------------- #


def python_files(name: str, pkg: str, kind: str) -> dict[str, str]:
    scripts = ""
    if kind in ("cli", "app"):
        scripts = f'\n[project.scripts]\n{name} = "{pkg}.cli:main"\n'

    files = {
        "pyproject.toml": f"""\
[project]
name = "{name}"
version = "0.1.0"
description = ""
readme = "README.md"
requires-python = ">=3.12"
dependencies = []
{scripts}
[dependency-groups]
dev = ["pytest>=8", "pytest-cov", "ruff", "mypy"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 100
src = ["src", "tests"]

[tool.ruff.lint]
# E,F  pycodestyle + pyflakes   I  import order      UP  modern syntax
# B    bugbear (real bugs)      SIM simplification   N   naming
# C4   comprehensions           PTH pathlib          TRY exception handling
select = ["E", "F", "I", "UP", "B", "SIM", "RUF", "N", "C4", "PTH", "ARG", "TRY"]

[tool.mypy]
strict = true
files = ["src", "tests"]

[tool.pytest.ini_options]
addopts = "-q --strict-markers"
testpaths = ["tests"]
""",
        f"src/{pkg}/__init__.py": f'"""{name}."""\n\n__version__ = "0.1.0"\n',
        f"src/{pkg}/py.typed": "",
        f"src/{pkg}/errors.py": f'''\
"""Exception hierarchy for {name}.

One base class per package lets a caller catch the whole family or one specific
failure, without matching on message strings.
"""


class {_camel(pkg)}Error(Exception):
    """Base for every error raised by this package."""


class ConfigError({_camel(pkg)}Error):
    """Configuration is missing or invalid."""
''',
        "tests/test_smoke.py": f"""\
from {pkg} import __version__


def test_package_imports() -> None:
    assert __version__
""",
        ".env.example": """\
# Copy to .env and fill in. Every variable the application reads belongs here,
# with a comment saying what it is for. Never commit real values.
LOG_LEVEL=INFO
""",
    }

    if kind in ("cli", "app"):
        files[f"src/{pkg}/cli.py"] = f'''\
"""Command-line entry point.

This module only translates argv into typed values and turns results into exit
codes. Keeping logic out of here means it stays testable without subprocesses.
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="{name}", description="TODO: describe.")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    logger.info("hello from {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

    if kind == "service":
        files[f"src/{pkg}/config.py"] = '''\
"""Configuration, loaded and validated once at startup.

Reading os.environ throughout the codebase turns a missing variable into a
KeyError hours into a run. Loading it here means the process fails immediately,
with a message naming what is missing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    log_level: str
    database_url: str

    @classmethod
    def from_env(cls) -> "Settings":
        try:
            return cls(
                log_level=os.environ.get("LOG_LEVEL", "INFO"),
                database_url=os.environ["DATABASE_URL"],
            )
        except KeyError as exc:
            raise RuntimeError(f"missing required environment variable: {exc.args[0]}") from exc
'''
        files["tests/conftest.py"] = '"""Shared fixtures live here."""\n'

    return files


def node_files(name: str, kind: str) -> dict[str, str]:
    is_lib = kind == "lib"
    return {
        "package.json": f"""\
{{
  "name": "{name}",
  "version": "0.1.0",
  "type": "module",
  "main": "dist/index.js",
  "types": "dist/index.d.ts",
  "scripts": {{
    "build": "tsc -p tsconfig.json",
    "dev": "tsx watch src/index.ts",
    "start": "node dist/index.js",
    "lint": "eslint . --max-warnings 0",
    "format": "prettier --write .",
    "typecheck": "tsc --noEmit",
    "test": "vitest run"
  }},
  "devDependencies": {{
    "@types/node": "^22",
    "eslint": "^9",
    "prettier": "^3",
    "tsx": "^4",
    "typescript": "^5",
    "vitest": "^2"
  }}
}}
""",
        "tsconfig.json": """\
{
  "compilerOptions": {
    "target": "ES2023",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "outDir": "dist",
    "rootDir": "src",
    "strict": true,
    // Without this, arr[i] is typed T even out of bounds — the type system
    // would otherwise hide the most common source of runtime undefined.
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "noImplicitOverride": true,
    "declaration": true,
    "sourceMap": true,
    "skipLibCheck": true
  },
  "include": ["src"],
  "exclude": ["node_modules", "dist"]
}
""",
        "src/index.ts": (
            "export { greet } from './greet.js';\n"
            if is_lib
            else """\
import { greet } from './greet.js';

function main(): void {
  console.log(greet('world'));
}

main();
"""
        ),
        "src/greet.ts": """\
export function greet(name: string): string {
  return `hello, ${name}`;
}
""",
        "src/greet.test.ts": """\
import { describe, expect, it } from 'vitest';
import { greet } from './greet.js';

describe('greet', () => {
  it('addresses the given name', () => {
    expect(greet('ada')).toBe('hello, ada');
  });
});
""",
        ".env.example": "# Copy to .env and fill in. Never commit real values.\nLOG_LEVEL=info\n",
    }


def go_files(name: str, kind: str) -> dict[str, str]:
    mod = name.replace("_", "-")
    files = {
        "go.mod": f"module github.com/CHANGEME/{mod}\n\ngo 1.23\n",
        "Makefile": """\
.PHONY: fmt vet test build
fmt:   ; gofmt -w .
vet:   ; go vet ./...
test:  ; go test -race -cover ./...
build: ; go build -o bin/ ./cmd/...
""",
        "internal/greet/greet.go": """\
// Package greet renders user-facing greetings.
package greet

import "fmt"

// Greet returns a greeting for name.
func Greet(name string) string {
	return fmt.Sprintf("hello, %s", name)
}
""",
        "internal/greet/greet_test.go": """\
package greet

import "testing"

func TestGreet(t *testing.T) {
	got := Greet("ada")
	want := "hello, ada"
	if got != want {
		t.Errorf("Greet() = %q, want %q", got, want)
	}
}
""",
    }
    if kind != "lib":
        files[f"cmd/{mod}/main.go"] = f"""\
// Command {mod} is the entry point. It wires dependencies and starts the
// program; all logic lives in internal packages so it can be tested directly.
package main

import (
	"fmt"
	"os"

	"github.com/CHANGEME/{mod}/internal/greet"
)

func main() {{
	if err := run(); err != nil {{
		fmt.Fprintf(os.Stderr, "{mod}: %v\\n", err)
		os.Exit(1)
	}}
}}

func run() error {{
	fmt.Println(greet.Greet("world"))
	return nil
}}
"""
    return files


def rust_files(name: str, kind: str) -> dict[str, str]:
    crate = name.replace("-", "_")
    files = {
        "Cargo.toml": f"""\
[package]
name = "{name}"
version = "0.1.0"
edition = "2021"

[dependencies]

[dev-dependencies]
""",
        "src/lib.rs": f"""\
//! {name}

/// Returns a greeting for `name`.
pub fn greet(name: &str) -> String {{
    format!("hello, {{name}}")
}}

#[cfg(test)]
mod tests {{
    use super::*;

    #[test]
    fn greets_the_given_name() {{
        assert_eq!(greet("ada"), "hello, ada");
    }}
}}
""",
    }
    if kind != "lib":
        files["src/main.rs"] = f"""\
use {crate}::greet;

fn main() {{
    println!("{{}}", greet("world"));
}}
"""
    return files


# --------------------------------------------------------------------------- #


def _camel(s: str) -> str:
    return "".join(part.capitalize() for part in re.split(r"[_\-]+", s) if part)


def build(name: str, lang: str, kind: str) -> dict[str, str]:
    pkg = re.sub(r"[^a-z0-9_]", "_", name.lower().replace("-", "_"))

    if lang == "python":
        files = python_files(name, pkg, kind)
        run_cmd = "uv sync\nuv run " + (name if kind in ("cli", "app") else f"python -c 'import {pkg}'")
        test_cmd = "uv run ruff format . && uv run ruff check . && uv run mypy src && uv run pytest"
    elif lang == "node":
        files = node_files(name, kind)
        run_cmd = "pnpm install\npnpm run dev"
        test_cmd = "pnpm run lint && pnpm run typecheck && pnpm run test"
    elif lang == "go":
        files = go_files(name, kind)
        run_cmd = f"go run ./cmd/{name.replace('_', '-')}"
        test_cmd = "gofmt -l . && go vet ./... && go test -race ./..."
    else:
        files = rust_files(name, kind)
        run_cmd = "cargo run"
        test_cmd = "cargo fmt --check && cargo clippy -- -D warnings && cargo test"

    files["README.md"] = readme(name, lang, kind, run_cmd, test_cmd)
    files[".gitignore"] = GITIGNORE_COMMON + "\n" + GITIGNORE[lang]
    files[".editorconfig"] = EDITORCONFIG
    files[".github/workflows/ci.yml"] = CI[lang]
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", required=True, help="Project name, e.g. my-project")
    parser.add_argument("--lang", required=True, choices=LANGS)
    parser.add_argument("--kind", default="app", choices=KINDS)
    parser.add_argument("--dir", default=".", help="Target directory (default: current)")
    parser.add_argument("--dry-run", action="store_true", help="Print the tree, write nothing")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    args = parser.parse_args(argv)

    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", args.name):
        print(
            f"error: --name {args.name!r} must be lowercase and start with a letter or "
            "digit (letters, digits, '.', '-', '_')",
            file=sys.stderr,
        )
        return 2

    root = Path(args.dir).resolve()
    files = build(args.name, args.lang, args.kind)

    if args.dry_run:
        print(f"{root}/")
        for path in sorted(files):
            print(f"  {path}")
        print(f"\n{len(files)} files. Re-run without --dry-run to write them.")
        return 0

    existing = [p for p in sorted(files) if (root / p).exists()]
    if existing and not args.force:
        print("error: refusing to overwrite existing files:", file=sys.stderr)
        for p in existing:
            print(f"  {p}", file=sys.stderr)
        print("\nPass --force to overwrite, or --dir to write elsewhere.", file=sys.stderr)
        return 1

    for path, content in sorted(files.items()):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        print(f"created {path}")

    print(
        f"\n{len(files)} files written to {root}.\n"
        "Next: choose a LICENSE and add it, fill in the README, then make the "
        "first commit before writing code."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
