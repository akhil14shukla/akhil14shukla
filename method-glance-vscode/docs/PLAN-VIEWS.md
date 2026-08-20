# Plan: four more views

## The decision that shapes everything

**One renderer, not five.** Every view emits the same primitives, so the webview
gains no per-view code and each new view is a layout function plus a test:

| Primitive | Used by |
| --- | --- |
| `node` — box with title, optional subtitle, optional row list | all |
| `edge` — polyline with optional label, arrowhead, style | all |
| `lane` — vertical guide with a header | sequence |
| `divider` — labelled horizontal rule | graph, modules |

A view is therefore: `GlanceModel → Scene`. Pure, testable under Node, no DOM.

## Step 0 — Scene abstraction + view switcher

Groundwork, no new views. Existing call graph must render identically after it.

- `src/scene.ts` — `Scene`, `SceneNode`, `SceneEdge`, `Lane`; adapter from the
  current `LayoutResult`.
- `media/glance.js` — render from Scene primitives; add row lists, edge labels,
  edge styles, lanes.
- `src/panel.ts` — view state, a `<select>` in the toolbar, dispatch per view.
- Mermaid export becomes per-kind (`flowchart` / `sequenceDiagram` / `classDiagram`).

## Step 1 — Sequence view

Answers *what happens when this runs*.

- Pick an entry point (auto: the method at the cursor, else the first detected
  entry point). Walk `provideOutgoingCalls` depth-first to a depth limit.
- Participants are lifelines in first-appearance order; messages are calls in
  source order, numbered, with activation bars by depth.
- **Honesty:** this is *static* call order, not a runtime trace. Calls sitting
  inside a branch or loop are marked conditional/repeated — derived from the
  call-site line's indent relative to the method body — and the caption says so.
- Self-calls render as a loop arrow; recursion is depth-capped.

## Step 2 — Class diagram

- Classes from `typesFromSymbols`, methods grouped by `container`, attributes
  harvested from `self.<name> =` assignments.
- Inheritance from `prepareTypeHierarchy` + `provideSupertypes` — both already
  written in `semantics.ts` and currently unused.
- Layered by inheritance depth, supertypes above; external supertypes dashed.

## Step 3 — Data-flow view

The hardest and the most approximate, so it is scoped tightly.

- **One method at a time** (the one at the cursor), not the whole file.
- Text-level def-use: parameters → locals that reference them → sinks (calls,
  returns, `self.` writes). Two hops of propagation.
- Three columns: parameters, intermediates, sinks.
- **Honesty:** heuristic, and labelled as such in the caption. It cannot see
  aliasing through containers or reassignment inside branches.

## Step 4 — Module map

- Imports parsed from the file, plus cross-file callees grouped by module from
  `CallEdge.externalUri`.
- Classified local / third-party / stdlib by path (`site-packages`,
  `node_modules`, relative path, absence from the workspace).
- Edge weight = number of resolved calls into that module. Imports with no
  resolved call are shown unweighted, since an unused import is worth seeing.

## Order and why

Sequence first — it is the view that answers the question a folded file still
cannot. Classes second, because the inheritance plumbing already exists. Data
flow third, since it needs new analysis. Modules last, being the only view that
reaches outside the document.
