---
name: code-craft
description: Write and edit source code in any language to a standard a stranger can read and change safely — naming, function shape, error handling, control flow, module boundaries, and when to restructure instead of patch. Use whenever the deliverable is source code in TypeScript, JavaScript, Go, Rust, Java, C#, C++, Ruby, PHP, Kotlin, Swift, shell, or SQL, including "quick" scripts and small edits. For Python use python-engineering instead. Trigger on "implement", "add a feature", "write a function", "refactor", "clean this up", "fix this code", or any request that ends in a code file changing.
---

# Code craft

Someone who has never seen this codebase will open your file at 2am with a
production incident open, read one function, and decide whether it is the cause.
They have no context and cannot ask you anything. Everything below serves that
moment.

The three failure modes that actually cause damage, in order: **code whose
behaviour differs from what its name and shape suggest**, **code that silently
does nothing when it fails**, and **code you must read five files to
understand.** Optimise against those before anything else.

## Before you write a line

- **Read two or three neighbouring files.** Match their naming, error handling,
  and structure. A technically better pattern applied inconsistently makes the
  codebase worse — if you want to introduce one, say so and apply it to a whole
  seam, not one file.
- **Search for the concept, not the name.** A date formatter might be
  `formatDate`, `toDisplayDate`, or `humanize`. Duplicated logic is the most
  expensive habit, because the two copies get fixed at different times.
- **Restate the requirement as a testable sentence.** If you cannot, you do not
  yet know what to build — ask, or state the assumption you are proceeding under.

## The standing rules

1. **Names say what a thing is or does, in domain language** — never its type.
   Length scales with scope; booleans read as assertions (`isExpired`); units go
   in the name (`timeoutSeconds`, `priceCents`); verbs signal cost (`get` is
   cheap, `fetch` does I/O). Never `data`, `info`, `manager`, `util`, `helper`.
2. **One job at one altitude per function.** Either orchestrate named steps or do
   detailed work, not both. Where a comment wanted to go is where a function
   wants to be extracted.
3. **No boolean parameters.** `render(doc, true)` is unreadable at the call site.
   Split the function or pass a named option.
4. **Guard clauses first, main line last and unindented.** Nesting past three
   levels means a guard or an extraction is missing.
5. **Separate decisions from effects.** A function that computes what should
   happen, plus a thin caller that does it, is testable without mocks. Push I/O
   to the edges; keep the middle pure. This is the biggest single lever on
   testability.
6. **Distinguish expected outcomes from failures.** "Not found" belongs in the
   return type; "connection refused" is an error that travels. Validate at the
   boundary so internal code can trust its inputs.
7. **Never swallow an error.** An empty catch converts a loud bug into a silent
   wrong answer. Add context as it travels up and preserve the cause; never log
   and rethrow. If ignoring is genuinely correct, write the one line saying why.
8. **Clean up with the language's scoped mechanism** — `defer`,
   `try-with-resources`, `using`, RAII, `finally` — never by hand on each return
   path, because someone will add a sixth return and miss it.
9. **Comment *why*, never *what*.** A comment explaining a line is a renaming
   opportunity. Document invariants, non-obvious constraints, and the issue link
   behind a workaround. `TODO`s carry an owner and a condition.
10. **Make illegal states unrepresentable.** Model the states themselves rather
    than a flag plus an optional field, so the compiler rejects the impossible
    combination instead of you writing a check you will forget somewhere.

## Before you call it done

Read your own diff as if hunting for the bug. What happens on empty input, a
missing key, a huge value, a concurrent second call? Is every error path handled
or deliberately propagated? Does anything leak on the error path, or log a
secret? Is there leftover debug output or an unexplained magic number?

## Read the reference that matches your task

| If you are… | Read |
|---|---|
| Naming things, shaping functions, or told the code is hard to follow | `references/naming-and-functions.md` |
| Writing in a specific language and want its rules and footguns | `references/languages/` — one file each: `typescript`, `go`, `rust`, `java`, `csharp`, `ruby`, `shell`, `sql` |
| Handling failure, validating input, or adding retries and timeouts | `references/errors-and-boundaries.md` |
| Deciding where code belongs, managing state or dependencies, or considering a rewrite | `references/structure-and-change.md` |
| Unsure why a construct reads badly | `references/anti-patterns.md` |

Adjacent skills: `repo-architect` for repository structure, `testing-craft` for
the tests, `perf-engineering` when it needs to be fast, `ship-quality` for the
pre-commit gate.
