# Changelog

## [0.1.0] - 2026-08-16

Initial release.

- Fold command that collapses method bodies while keeping signatures and
  docstrings visible, plus an unfold command to restore.
- Python support: docstring-aware folding, multi-line signatures, `async def`,
  `"""`/`'''` and prefixed string forms, nested definitions.
- Best-effort support for brace-delimited languages: JavaScript, TypeScript,
  JSX/TSX, Java, C, C++, C#, Go, Rust, PHP, Kotlin, Scala, Swift, Dart, Groovy.
  Control-flow blocks and class bodies are left expanded.
- `methodGlance.foldOnOpen` setting to fold automatically on opening a file.
- Default keybindings `Ctrl+K Ctrl+G` / `Ctrl+K Ctrl+U`.
