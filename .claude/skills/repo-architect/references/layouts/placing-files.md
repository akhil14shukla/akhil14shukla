# Placing a new file

Read this when you have written something and are deciding where it goes, or
when a directory is filling up and you are unsure whether to split it.

Working rules that settle most arguments in seconds:

- **A file goes next to the code that uses it**, unless more than one domain
  uses it — then it moves up one level, no further.
- **Create a directory at the third related file, not the first.** Two files can
  sit beside each other; a directory containing one file is noise, and premature
  directories are as bad as premature abstraction.
- **Depth beyond three or four levels below `src/` is a smell.**
  `src/a/b/c/d/e/thing.py` means the hierarchy is doing work that naming should
  do.
- **Tests mirror source**: `src/orders/pricing.py` → `tests/orders/test_pricing.py`,
  so a reader never has to search for a file's test. Where the ecosystem
  co-locates tests instead — Go's `_test.go`, Rust's `#[cfg(test)]`, a frontend's
  `Component.test.tsx` — follow the ecosystem; consistency with it beats
  consistency with this document.
- **One concept per file.** Three unrelated classes should be three files; a
  class plus its two small value objects is one file.
- **File names match what they contain**, in the language's casing convention:
  `snake_case.py`, `kebab-case.ts` or `PascalCase.tsx` for components,
  `lowercase.go`, `snake_case.rs`. Never `misc`, `helpers`, `stuff`, `temp`,
  `new_`, `v2`, or a person's name.
