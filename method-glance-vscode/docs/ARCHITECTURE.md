# Architecture

## The rule

**Every view renders from `GlanceModel` (`src/model.ts`).** Nothing that draws
knows where the facts came from. That is what makes new visuals cheap: a diagram
is a new renderer over an existing model, not a new parser.

```
   language server (Pylance, tsserver, gopls, rust-analyzer, …)
            │  DocumentSymbol · CallHierarchy · TypeHierarchy · Diagnostics
            ▼
   src/semantics.ts ──── cache keyed on doc.version
            │                    ▲
            │  falls back to     │
            ▼                    │
   src/textSource.ts ── src/pythonParser.ts · src/braceParser.ts
            │
            ▼
        GlanceModel  ──►  folding · hover · carets · (panels)
```

## Why semantics first

The original implementation parsed everything itself. That was wrong in the ways
that matter for a call graph: text matching on `self._foo(` cannot see
inheritance, `super()`, aliases, decorators, or imports — exactly the cases where
knowing the call graph is most valuable.

VS Code core has no AST for Python; it ships TextMate grammars for coloring and
nothing more. The real understanding lives in the language server, reachable
through documented provider commands.

| Command | Yields | Feeds |
| --- | --- | --- |
| `executeDocumentSymbolProvider` | method ranges, kinds, containers, signatures | folding, outline, node sizing |
| `prepareCallHierarchy` + `provideOutgoingCalls` / `provideIncomingCalls` | type-resolved call edges, cross-file | flow graph, sequence diagram |
| `prepareTypeHierarchy` + `provideSupertypes` | inheritance | class diagram |
| `languages.getDiagnostics` | errors/warnings per range | node status color |
| `executeReferenceProvider` | fan-in count | node weight, hot-path emphasis |

Symbols-first also made language support nearly free — any language with a
symbol provider works, including ones never listed in `languages.ts`.

## What the parsers are still for

They are not dead code. They cover the cases the semantic path cannot:

- No language extension installed for the file.
- Server still starting — symbol lookup is raced against a 1.5s timeout.
- A language whose server implements symbols but not call hierarchy.

Both paths produce identical `MethodNode` shapes, and `origin` records which ran
so a degraded view is never presented as an exact one.

## The one thing no API provides

No provider answers *"where does the docstring end."* `DocumentSymbol.range` is
one span covering signature, docstring, and body. `src/docs.ts` resolves that
boundary — the irreducible text logic, now ~15 lines against a range someone
else computed correctly, rather than 200 lines of hunting for `def`.

Two subtleties it handles: decorators sit inside `range.start`, so the fold point
is anchored to `selectionRange` instead; and some servers fold a doc comment into
the symbol range while others leave it above, so brace-language doc lookup
anchors to the signature line.

## Cost discipline

Call hierarchy is **one request per method**. A 40-method file is 40 round trips,
so it is never computed eagerly for a whole file:

- Structure (`getModel`) is cheap and cached on `doc.version`.
- Edges resolve lazily — on hover, or when a panel opens — and merge into the
  cached model, so repeat hovers are free.
- Gutter carets are capped by `DECORATION_BUDGET`.

## The logic skeleton

A call graph answers *what calls what*. It says nothing about **what a function
does** — and that is usually the question. `src/shape.ts` reads each body's
structure and reports it next to the docstring, so a folded file says:

```
def _charge(self, user, amount):
    """Capture payment; raises PaymentError on decline."""…    1 catch · 1 guard · net log

def _persist(self, cart, user, total):
    """Write the order row and return the saved Order."""…    mutates · db
```

Neither the name nor the docstring told you that one method talks to the network
and the other writes to the database.

It measures decision points, loops, error handlers, early exits, generators,
awaits, nesting depth, cyclomatic complexity, instance-state mutation, and side
effects (io, net, db, proc, log, time, random).

Three decisions worth recording:

- **Text-level on purpose.** Control-flow keywords are unambiguous once comments
  and string bodies are stripped, and this way the skeleton works with no
  language server running — the one signal that is always available.
- **Literals are stripped before counting.** A docstring saying "if" and a URL
  containing "post" must not register as a branch and a network call. This is
  the single largest source of false readings, and it is tested directly.
- **A nested helper is measured as its own method**, so an outer function is not
  blamed for its helper's complexity.

Entry points — `main`, route/CLI/task decorators, `test_` prefixes — are detected
too. In a strange file, "where does this start" is the first question, and the
map marks those nodes.

## Visual roadmap

Everything renders from the same model. Ordered by value per unit of work.

### Built

- **Glance Map panel** — call graph, click to jump, hover to trace.
- **Logic skeleton** — inline in the editor and in map subtitles.
- **Entry points** — marked in the map.
- **Mermaid export.**

### Still ahead

### 1. Sequence view

Pick an entry point, walk `provideOutgoingCalls` breadth-first to a depth limit,
render lifelines in call order. This is the view that answers "what actually
happens when this runs" — the thing a folded file still cannot show.

### 2. Class diagram

`prepareTypeHierarchy` + `provideSupertypes` across the file's classes, with
methods grouped under their owner. Cheap once the type edges exist.

### 3. Data-flow view

Which parameters reach which calls. The remaining question the skeleton does not
answer: not *what* a function touches, but *how the values move through it*.
Needs real expression-level analysis, so it is the most expensive item here.

### 4. Module map

Fan out one hop through cross-file call edges to show which modules this file
actually reaches. The only view that needs multi-document resolution.

### Rendering choice

Deterministic layout for everything above — bundled locally, no network, CSP-safe
in a webview. A code map is a navigator; a hallucinated edge is worse than no
edge, and the same file must produce the same picture every time.

Mermaid is worth bundling alongside as an **export** format (its flowchart,
sequence, and class syntaxes map onto views 1–3), so a diagram can be pasted into
a PR or a doc as text.

### Where generative diagrams fit

`mcp-image-thinking` is an agent-facing tool: an LLM writes SVG, which is then
sanitized and rasterized. That makes it excellent for *explaining* a gnarly flow
in prose-plus-picture, and unsuitable for the always-on rendering path — it needs
an API key, takes seconds, costs tokens, and is not reproducible.

If it earns a place in the extension it is as one opt-in command — "Explain this
flow" — that sends an already-extracted, factual subgraph (not raw source) and
returns an illustrative diagram clearly marked as generated. The exact views stay
deterministic.
