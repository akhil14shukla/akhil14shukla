# TypeScript / JavaScript

The rules that separate code a maintainer trusts from code that merely runs in TypeScript / JavaScript, plus the footguns that cause real production bugs.

**Use TypeScript, in strict mode.** `"strict": true` plus
`noUncheckedIndexedAccess` and `exactOptionalPropertyTypes` in `tsconfig.json`.
Without `noUncheckedIndexedAccess`, `arr[i]` is typed as `T` even when the index
is out of bounds, and the type system actively lies to you about the most common
source of runtime `undefined`.

**Types**

- Never `any`. Use `unknown` at boundaries and narrow it — `unknown` forces the
  check, `any` silently disables the compiler for everything downstream.
- Prefer discriminated unions over optional fields for state:
  ```ts
  // Lets you construct a "success" with an error attached.
  type Result = { ok: boolean; value?: User; error?: Error };

  // The impossible states no longer typecheck.
  type Result =
    | { ok: true; value: User }
    | { ok: false; error: Error };
  ```
- `type` for unions and function shapes, `interface` for object contracts that
  others implement or augment. Do not churn a codebase to convert between them.
- Derive, don't duplicate: `keyof`, `typeof`, `Pick`, `Omit`, `ReturnType`,
  and `as const` keep types in sync with the values they describe.
- Validate external data at the edge with a schema library (zod, valibot) and
  infer the type from the schema. A hand-written `interface` over an API
  response is a claim, not a check — the moment the API changes, your types are
  fiction.
- `satisfies` when you want a value checked against a type without widening it.

**Runtime and async**

- `===` always. `==` only for the deliberate `x == null` null-or-undefined check.
- `async`/`await` over `.then()` chains; mixing them in one function is how
  unhandled rejections appear. Every `await` that can reject is inside a `try`
  or is deliberately propagated.
- `Promise.all` rejects on the first failure and abandons the rest — use
  `Promise.allSettled` when you need every outcome. Never `await` inside a loop
  when the iterations are independent; collect promises and await once.
- A floating promise (calling an async function without awaiting or catching) is
  a crash waiting for the right timing. Enable
  `@typescript-eslint/no-floating-promises`.
- `structuredClone` for deep copies; the `JSON.parse(JSON.stringify(x))` idiom
  silently destroys `Date`, `Map`, `Set`, `undefined`, and `BigInt`.
- Money is never a `number`. IEEE-754 makes `0.1 + 0.2 !== 0.3`; use integer
  minor units or a decimal library.

**Modules**

- Named exports over default exports: they rename consistently, autocomplete,
  and survive refactors.
- Wide barrel files (`index.ts` re-exporting everything) wreck tree-shaking and
  create import cycles. A barrel at a *feature's* root exposing that feature's
  public surface is fine and useful; a repo-wide `src/index.ts` is not.
- Node built-ins get the `node:` prefix (`import fs from "node:fs/promises"`) so
  the intent is unambiguous and no npm package can shadow them.

**Tooling baseline**: TypeScript strict, ESLint (typescript-eslint), Prettier or
Biome, Vitest or Jest, and one package manager committed with its lockfile.
