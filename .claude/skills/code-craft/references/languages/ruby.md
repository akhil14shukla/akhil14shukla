# Ruby

The rules that separate code a maintainer trusts from code that merely runs in Ruby, plus the footguns that cause real production bugs.

- Small methods, meaningful names, and `frozen_string_literal: true` at the top
  of every file.
- Prefer keyword arguments for anything with more than one parameter — Ruby
  call sites are otherwise unreadable.
- `Struct`/`Data.define` for value objects rather than passing hashes around;
  a hash with string keys crossing three methods is an undocumented type.
- Rescue specific error classes. A bare `rescue` catches `StandardError` and
  hides real bugs; `rescue Exception` also catches interrupts and is almost
  always wrong.
- Guard clauses and `return` early; avoid `unless` with a compound condition.
- Rails: keep controllers thin (params → service → response), push logic into
  POROs or service objects rather than fat models, and always paginate.
  `includes` to kill N+1 queries — see `perf-engineering`.

**Tooling baseline**: RuboCop, RSpec or Minitest, Sorbet or RBS if the codebase
is large.
