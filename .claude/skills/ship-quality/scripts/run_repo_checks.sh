#!/usr/bin/env bash
# Detect and run this repository's own format / lint / typecheck / test gates.
#
# The point is to run exactly what CI runs, so that green here means green
# there. It never invents commands: it reads the Makefile, package.json scripts,
# pyproject.toml, go.mod, and Cargo.toml, and runs what it finds.
#
#   run_repo_checks.sh            run every gate it detects
#   run_repo_checks.sh --list     print what it would run, run nothing
#   run_repo_checks.sh --fix      allow formatters to rewrite files
#
# Exit code is 0 only if every detected gate passed.

set -uo pipefail

LIST_ONLY=0
FIX=0
for arg in "$@"; do
  case "$arg" in
    --list) LIST_ONLY=1 ;;
    --fix)  FIX=1 ;;
    -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

if ! root=$(git rev-parse --show-toplevel 2>/dev/null); then
  root=$PWD
  echo "note: not a git repository; using $root" >&2
fi
cd "$root" || exit 1

NAMES=()
CMDS=()
COVERED=""

# add <display name> <command> <concern>
# The concern (fmt|lint|types|test) prevents running the same gate twice when a
# Makefile target and an inferred command both cover it. The repository's own
# entry point wins, because that is what its CI runs.
add() {
  local concern="${3:-}"
  if [[ -n "$concern" && " $COVERED " == *" $concern "* ]]; then return 0; fi
  NAMES+=("$1"); CMDS+=("$2")
  [[ -n "$concern" ]] && COVERED="$COVERED $concern"
  return 0
}
has() { command -v "$1" >/dev/null 2>&1; }

# --- Makefile: the repo's own entry points win over anything we infer --------
if [[ -f Makefile ]]; then
  targets=$(grep -oE '^[a-zA-Z0-9_.-]+:' Makefile | tr -d ':' | sort -u)
  for t in fmt format lint vet typecheck types test; do
    grep -qx "$t" <<<"$targets" || continue
    case "$t" in
      # A `make fmt` target normally rewrites files, so run it only under --fix;
      # in check mode the language block below adds a non-destructive equivalent.
      fmt|format)        (( FIX )) && add "make $t" "make $t" fmt ;;
      lint|vet)          add "make $t" "make $t" lint ;;
      typecheck|types)   add "make $t" "make $t" types ;;
      test)              add "make $t" "make $t" test ;;
    esac
  done
fi

# --- Node / TypeScript ------------------------------------------------------
if [[ -f package.json ]]; then
  if has pnpm && [[ -f pnpm-lock.yaml ]]; then pm="pnpm"
  elif has yarn && [[ -f yarn.lock ]];      then pm="yarn"
  elif has bun  && [[ -f bun.lockb ]];      then pm="bun run"
  else pm="npm run"; fi

  scripts=$(python3 - <<'PY' 2>/dev/null || true
import json, pathlib
try:
    data = json.loads(pathlib.Path("package.json").read_text(encoding="utf-8"))
    print("\n".join(data.get("scripts", {})))
except Exception:
    pass
PY
)
  [[ -z "$scripts" ]] && scripts=$(grep -oE '"[a-zA-Z0-9:_-]+"[[:space:]]*:' package.json | tr -d '":' | tr -d ' ')

  for s in format lint typecheck type-check types test; do
    if grep -qx "$s" <<<"$scripts"; then
      [[ $s == format ]] && (( ! FIX )) && continue
      case "$s" in
        format) add "$pm $s" "$pm $s" fmt ;;
        lint) add "$pm $s" "$pm $s" lint ;;
        typecheck|type-check|types) add "$pm $s" "$pm $s" types ;;
        test) add "$pm $s" "$pm $s" test ;;
      esac
    fi
  done
  if ! grep -qxE 'typecheck|type-check|types' <<<"$scripts" && [[ -f tsconfig.json ]]; then
    add "tsc --noEmit" "npx --no-install tsc --noEmit" types
  fi
fi

# --- Python -----------------------------------------------------------------
if [[ -f pyproject.toml || -n $(find . -maxdepth 2 -name '*.py' -not -path './.git/*' -print -quit 2>/dev/null) ]]; then
  run=""
  if has uv && [[ -f uv.lock ]]; then run="uv run "; fi

  if has ruff || grep -q '\[tool\.ruff' pyproject.toml 2>/dev/null; then
    if (( FIX )); then
      add "ruff format" "${run}ruff format ." fmt
      add "ruff check --fix" "${run}ruff check --fix ." lint
    else
      add "ruff format --check" "${run}ruff format --check ." fmt
      add "ruff check" "${run}ruff check ." lint
    fi
  fi
  if grep -q '\[tool\.mypy' pyproject.toml 2>/dev/null || [[ -f mypy.ini ]]; then
    target="src"; [[ -d src ]] || target="."
    add "mypy" "${run}mypy $target" types
  elif grep -q '\[tool\.pyright' pyproject.toml 2>/dev/null || [[ -f pyrightconfig.json ]]; then
    add "pyright" "${run}pyright" types
  fi
  if [[ -d tests ]] || grep -q '\[tool\.pytest' pyproject.toml 2>/dev/null || [[ -f pytest.ini ]]; then
    add "pytest" "${run}pytest" test
  fi
fi

# --- Go ---------------------------------------------------------------------
if [[ -f go.mod ]]; then
  add "gofmt" 'test -z "$(gofmt -l .)" || { gofmt -l .; false; }' fmt
  add "go vet" "go vet ./..." lint
  has staticcheck && add "staticcheck" "staticcheck ./..." lint
  add "go test -race" "go test -race ./..." test
fi

# --- Rust -------------------------------------------------------------------
if [[ -f Cargo.toml ]]; then
  if (( FIX )); then add "cargo fmt" "cargo fmt" fmt; else add "cargo fmt --check" "cargo fmt --check" fmt; fi
  add "cargo clippy" "cargo clippy --all-targets -- -D warnings" lint
  add "cargo test" "cargo test" test
fi

# --- pre-commit covers many of the above in one go --------------------------
if [[ -f .pre-commit-config.yaml ]] && has pre-commit; then
  add "pre-commit" "pre-commit run --all-files"
fi

# --- Report -----------------------------------------------------------------
if (( ${#NAMES[@]} == 0 )); then
  echo "No checks detected in $root."
  echo
  echo "Read the CI workflow to find what this repository actually runs:"
  ls .github/workflows/*.y*ml 2>/dev/null || echo "  (no .github/workflows found)"
  exit 0
fi

if (( LIST_ONLY )); then
  echo "Would run ${#NAMES[@]} check(s) in $root:"
  for i in "${!NAMES[@]}"; do printf '  %-24s %s\n' "${NAMES[$i]}" "${CMDS[$i]}"; done
  exit 0
fi

failed=()
for i in "${!NAMES[@]}"; do
  printf '\n\033[1m── %s ──\033[0m\n' "${NAMES[$i]}"
  if eval "${CMDS[$i]}"; then
    printf '\033[32mPASS\033[0m %s\n' "${NAMES[$i]}"
  else
    printf '\033[31mFAIL\033[0m %s\n' "${NAMES[$i]}"
    failed+=("${NAMES[$i]}")
  fi
done

echo
echo "──────────────────────────────────────────"
if (( ${#failed[@]} == 0 )); then
  printf '\033[32mAll %d check(s) passed.\033[0m\n' "${#NAMES[@]}"
  exit 0
fi
printf '\033[31m%d of %d check(s) failed:\033[0m\n' "${#failed[@]}" "${#NAMES[@]}"
printf '  %s\n' "${failed[@]}"
echo
echo "Fix these before committing. Do not skip or weaken a test to get green —"
echo "if a failure predates your change, verify that (git stash; re-run) and say so."
exit 1
