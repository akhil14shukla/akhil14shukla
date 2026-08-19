# Architecture decisions

Read this when choosing a stack, deciding whether something is one service or
several, picking an API style or a datastore, or making any other choice that
would be expensive to undo.

## Contents

- [Verify currency before you choose](#verify-currency-before-you-choose)
- [The reversibility lens](#the-reversibility-lens)
- [One service or several](#one-service-or-several)
- [Building a monolith you can split later](#building-a-monolith-you-can-split-later)
- [Choosing an API style](#choosing-an-api-style)
- [Synchronous or event-driven](#synchronous-or-event-driven)
- [Choosing a datastore](#choosing-a-datastore)
- [Where state lives](#where-state-lives)
- [Record the decision](#record-the-decision)

## Verify currency before you choose

**Your knowledge of the ecosystem has a cutoff; the ecosystem does not.** Version
numbers, end-of-life dates, deprecations, security advisories, and which library
is the maintained one all move faster than any model's training data. Choosing a
framework from memory is how a project starts on a version that went end-of-life
eight months ago, or adopts a library whose maintainer archived it.

**Search the web before locking in any of these:** a language or runtime version,
a web framework, an ORM or database driver, an auth library, a build tool, a
datastore, a deployment target, an API style, or any dependency that will be
hard to remove. Tell the user you are doing it — "let me check what's current
before I pick" — because it costs a moment and prevents a rewrite.

What to establish, concretely:

- **Current stable version, and the end-of-life date for the one you would
  otherwise pick.** Starting on a version with twelve months left is a decision,
  not an accident.
- **Is it maintained?** Date of the last release and last commit; open issue
  count and whether maintainers reply. A library with no release in two years is
  a dependency you will end up owning.
- **Is this still the recommended approach**, or has the ecosystem moved? This
  is the one memory gets wrong most often — the "standard" tool for a job in one
  year is legacy in the next.
- **Breaking changes and migration notes** since the version you know.
- **Open security advisories.**

How to search so the answer is usable: query the thing plus the current year
(`"<library> 2026"`), plus `deprecated`, `alternatives`, or `vs <the option you
know>`; then confirm against the **primary source** — the official docs, the
release page, the repository's commit history — because blog posts date badly
and are often written to rank rather than to be right.

Then **say what you verified and when**: "Checked August 2026: Python 3.14 is
current, 3.12 is supported until 2028, and uv is the mainstream environment
tool." That timestamp is what lets a future reader know whether to re-check, and
it belongs in the ADR.

Do not search for things that do not move: a standard-library function, a
well-established pattern, an algorithm, or SQL semantics. Reserve it for choices
with a version number or a maintainer attached.

## The reversibility lens

Spend decision effort in proportion to how hard the decision is to undo.

- **Two-way doors** — a library you can swap behind an interface, a directory
  layout, a formatting convention, an internal API shape. Decide quickly, move
  on, change it later if you were wrong. Deliberating here is waste.
- **One-way doors** — your primary datastore, your language, your public API
  contract, your auth model, your data model's core entities, anything customers
  build against. These deserve research, a written comparison, and an ADR.

Most architecture paralysis is treating two-way doors as one-way. Most
architecture regret is the opposite.

## One service or several

**Default to one well-structured deployable.** The industry has spent a decade
learning this the expensive way, and by 2026 the consensus has moved decisively
back toward starting with a modular monolith: a single deployable with strict
internal boundaries. A 2025 CNCF survey found roughly 42% of organisations that
had adopted microservices were consolidating services back into larger units,
and Amazon's Prime Video video-quality team famously reported around a 90%
infrastructure cost reduction moving one microservice pipeline back to a
monolith. The pattern is not that microservices are wrong — it is that they were
adopted before the problems they solve had appeared.

**Split when you have a specific reason**, all of which are organisational or
physical rather than aesthetic:

- **Independent deploy cadence.** Multiple teams blocked on each other's release
  train. This is the strongest and most common legitimate reason.
- **Genuinely divergent scaling.** One part needs 50 machines and GPUs while the
  rest needs two. Paying for the whole monolith at that ratio is real money.
- **Compliance or data isolation** — a boundary a regulator will ask about.
- **Different reliability requirements** — a batch job must not be able to take
  down checkout.

**Do not split** because it sounds modern, because one team wants a different
language, or before the domain boundaries are actually understood. A distributed
system with the wrong boundaries is strictly worse than a monolith with the wrong
boundaries, because now the wrong boundary has a network in the middle of it,
with partial failure, versioning, and distributed debugging attached.

A rough guide by team size: under ~15 engineers, one modular deployable; 15–50,
one deployable with selective extraction of the parts that genuinely differ;
50+, service-per-team becomes worth its operational cost. Treat these as
prompts to think, not thresholds to obey.

## Building a monolith you can split later

This is the practical skill, and it costs almost nothing at the start. The aim
is that extraction, if it ever comes, is a deployment change rather than a
rewrite.

- **Module boundaries are real boundaries.** One directory per domain, a
  declared public surface, and everything else private. Enforce it with the
  language's mechanism — Go's `internal/`, Java package-private, Rust
  `pub(crate)`, an import-lint rule in Python or TypeScript.
- **No cross-module database access.** A module reads and writes *its own*
  tables. If orders needs customer data it calls the customer module's function,
  not its table. **Shared tables are what makes extraction impossible**, because
  a join across two modules becomes a distributed join across two services.
- **Talk through explicit interfaces**, not by reaching into another module's
  internals. The call is in-process today and could be a network call tomorrow —
  which also means designing it as a coarse operation, not a chatty getter.
- **Separate schemas per module** in one database instance gives you the
  boundary without the operational cost of many databases.
- **Keep the transaction boundary inside one module.** A transaction spanning two
  modules is the thing that cannot be split, and finding this out during
  extraction is expensive.

Follow these and extraction is mechanical. Skip them and "we'll split it later"
never happens, because later it is one thing.

## Choosing an API style

| Style | Choose when | Cost |
|---|---|---|
| **REST + OpenAPI** | The default. Public APIs, partner integrations, anything a browser calls directly | Chattier; over- and under-fetching |
| **GraphQL** | Many different clients need different slices of the same graph, and you control the schema | Query complexity, caching is harder, N+1 unless you add dataloaders |
| **gRPC** | Internal service-to-service where you own both ends and want a strict schema and speed | Not browser-native without a proxy; harder to debug by hand |
| **tRPC or equivalent** | Same-language monorepo, one client, end-to-end types | Couples client and server; no use outside that language |

Reach and familiarity beat raw performance whenever the caller includes a
browser, a third-party developer, or a partner you do not control — which is why
REST remains the default for anything public. Large systems legitimately end up
hybrid: gRPC between internal services, REST at the edge.

Whatever you pick: version it from day one, make additive changes only within a
version, document the error contract (callers branch on it), and paginate
anything that can grow.

## Synchronous or event-driven

Synchronous calls are simpler, easier to debug, and give the caller an immediate
answer. Use them by default.

Reach for events or a queue when: the work does not need to finish before the
user gets a response; several consumers need to react to one fact; the producer
should not know who consumes; or you need to absorb bursts.

The costs are real and must be designed for, not discovered:

- **Every consumer must be idempotent** — messages are delivered at least once,
  so retries happen and a duplicated charge is a real outcome.
- **Ordering is not guaranteed** unless you pay for it, usually with partition
  keys that then constrain your parallelism.
- **Failures are invisible without a dead-letter queue and an alert on it.**
- **Debugging spans processes** — you need correlation ids and tracing from the
  start, or an investigation becomes archaeology.
- **Eventual consistency becomes a product decision**, not just a technical one.
  Someone has to decide what the user sees in the window before consistency
  arrives.

A useful middle ground: synchronous API, with the slow part queued, and a status
the client can poll or subscribe to.

## Choosing a datastore

**A relational database is the default**, and the bar for deviating is high. It
gives you transactions, constraints, joins, mature tooling, and an escape hatch
via JSON columns for genuinely unstructured parts. Most "we need NoSQL for
scale" decisions are made at a scale where a single well-indexed Postgres
instance would have been fine for years.

Deviate for a specific shape of problem: a document store when documents are
genuinely independent and schema varies per record; a key-value store for
session and cache data with simple access patterns; a search engine when you
need relevance ranking and full-text scoring (usually *alongside* the relational
store, not instead of it); a time-series database for high-volume metrics with
time-window queries; a graph database when traversal depth is unbounded and
recursive joins are the main workload.

Two practical rules: **model the data by how it will be queried**, not only by
how it is conceptually structured; and **put the constraints in the schema** —
`NOT NULL`, foreign keys, unique indexes, `CHECK`. Application-level validation
alone always drifts, and the database is the only place that sees every writer.

## Where state lives

- **Keep the application tier stateless** so any instance can serve any request
  and scaling is a matter of count. Sessions in a shared store, not in process
  memory; uploads in object storage, not on local disk.
- **One source of truth per fact.** A value stored in two places diverges; derive
  the second or store it once.
- **Cache with a distance and a lifetime you can state.** See
  `perf-engineering`.
- **Configuration from the environment, validated into a typed object at
  startup** — see `references/boundaries-and-config.md`.

## Record the decision

Every one-way door gets an ADR: the context, the decision, the consequences you
accept, the alternatives you rejected and why, and the date you verified the
ecosystem facts. Six months later the code shows what was decided; only the ADR
shows why, and without it the team re-argues it. `docs-craft` has the template.
