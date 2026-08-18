# Shell (bash)

The rules that separate code a maintainer trusts from code that merely runs in Shell (bash), plus the footguns that cause real production bugs.

Shell is where "quick script" becomes an outage. If it exceeds ~100 lines or
needs data structures, rewrite it in Python or Go — that is not a failure, it
is the correct call.

```bash
#!/usr/bin/env bash
set -euo pipefail          # exit on error, undefined var, and failed pipe stage
IFS=$'\n\t'
```

- **Quote every expansion**: `"$var"`, `"$@"`, `"${arr[@]}"`. An unquoted
  variable containing a space becomes two arguments, and one containing `*`
  becomes your entire directory listing.
- `[[ ]]` over `[ ]`; `$(...)` over backticks.
- Check that required commands and variables exist up front, with a clear error,
  rather than failing halfway through with a cryptic message.
- Use `mktemp -d` for scratch space and `trap 'rm -rf "$tmp"' EXIT` to clean up
  on every exit path, including failure.
- Never `rm -rf "$dir/"*` without verifying `$dir` is non-empty and is what you
  think — this is the classic data-loss bug.
- `set -e` does not fire inside `if`, `&&`, or a function whose result is
  tested; check exit codes explicitly where it matters.
- Run **ShellCheck**. It catches most of the above mechanically.
