# Method Glance

A VS Code extension that folds everything **except method signatures and their
docstrings**, so you can skim a file and see what each method does without
scrolling through implementations.

## What it looks like

Before:

```python
class Repository:
    def find(self, id):
        """Return the record with the given id, or None."""
        row = self._db.execute("SELECT * FROM t WHERE id = ?", (id,))
        if row is None:
            return None
        return self._hydrate(row)

    def save(self, record):
        """Persist a record and return its assigned id."""
        payload = self._serialize(record)
        cursor = self._db.execute("INSERT INTO t VALUES (?)", (payload,))
        self._db.commit()
        return cursor.lastrowid
```

After running **Method Glance: Fold to Method Signatures & Docstrings**:

```python
class Repository:
    def find(self, id):
        """Return the record with the given id, or None."""…

    def save(self, record):
        """Persist a record and return its assigned id."""…
```

The signature and the docstring stay on screen; the body collapses behind the
`…` marker. Click the marker or run the unfold command to bring it back.

## Usage

| Command | Keybinding | Description |
| --- | --- | --- |
| `Method Glance: Fold to Method Signatures & Docstrings` | `Ctrl+K Ctrl+G` (`Cmd+K Cmd+G` on macOS) | Collapse every method body |
| `Method Glance: Unfold Everything` | `Ctrl+K Ctrl+U` (`Cmd+K Cmd+U` on macOS) | Expand everything again |

Both are also available from the Command Palette (`Ctrl+Shift+P`).

Folding is idempotent — running it twice gives the same result, because it
unfolds first and then re-folds.

## Settings

| Setting | Default | Description |
| --- | --- | --- |
| `methodGlance.foldOnOpen` | `false` | Automatically fold when a supported file becomes the active editor |
| `methodGlance.showCallCarets` | `true` | Mark methods that call a sibling with a gutter caret |

Hovering a folded method's signature shows its docstring plus what it calls and
who calls it.

## The logic skeleton

Folding tells you a method's name and docs. It does not tell you what the body
*does*. Method Glance annotates each folded method with its shape:

```
def _charge(self, user, amount):
    """Capture payment; raises PaymentError on decline."""…    1 catch · 1 guard · net log

def _persist(self, cart, user, total):
    """Write the order row and return the saved Order."""…    mutates · db
```

Branches, loops, error handlers, early exits, generators, awaits, complexity, and
side effects — io, net, db, proc, log, time, random. Hover the annotation for the
full breakdown. Anything over complexity 10 is flagged in the warning colour.

This is read from the text, so it works even with no language server running.
String and comment contents are stripped first, so a docstring mentioning "if"
or a URL containing "post" is never miscounted.

## The Glance Map

`Ctrl+K Ctrl+M` (`Cmd+K Cmd+M`) opens the call graph beside your file: callers
above callees, click a node to jump to it, hover to trace what it touches.

Entry points — `main`, route and CLI decorators, `test_` functions — are outlined,
because "where does this start" is the first question in an unfamiliar file.
Node width tracks method size, the subtitle shows side effects, dashed edges
cross file boundaries, and `Copy Mermaid` exports the diagram as text for a PR.

## Language support

**Python** is the primary target and gets the most precise handling:

- The signature and the docstring both stay visible; only the code after the
  docstring is hidden.
- Multi-line signatures (parameters spread over several lines) are handled by
  tracking bracket depth to find the `:` that actually ends the signature.
- Both `"""` and `'''` docstrings, single-line or multi-line, plus prefixed
  forms like `r"""` and `f"""`.
- `async def` as well as `def`, at any nesting depth.
- One-line bodies (`def noop(): return None`) are left alone — there is nothing
  to collapse.

**Brace-delimited languages** are supported on a best-effort basis: JavaScript,
TypeScript (and their React variants), Java, C, C++, C#, Go, Rust, PHP, Kotlin,
Scala, Swift, Dart, and Groovy. In these languages doc comments sit *above* the
signature rather than inside the body, so folding the `{ … }` body is enough to
keep both the comment and the signature visible.

The brace scanner is aware of strings, character literals, line and block
comments, and JavaScript template literals (including nested `${ }`
expressions), so braces appearing inside those don't throw off body matching.
Control-flow blocks (`if`, `for`, `while`, `switch`, `try`, …) and class bodies
are deliberately left expanded — collapsing a class body would hide the very
methods you are trying to glance at.

## How it works

Structure comes from **your language server** — Pylance, tsserver, gopls,
rust-analyzer — through VS Code's provider commands, not from parsing text.
`executeDocumentSymbolProvider` gives exact method ranges; call hierarchy gives
type-resolved call edges that handle inheritance, `super()`, aliases and imports.
The bundled parsers remain as a fallback for files with no language extension
installed, or a server that has not finished starting.

Because structure is read from symbols, languages with a symbol provider work
even if they are not in the list above.

Folding ranges are additive: your normal folding controls keep working exactly as
before, and nothing is ever modified in your file — this is purely a view
operation.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the data flow, the cost
model behind lazy call resolution, and the roadmap for diagram views.

## Development

```bash
npm install
npm run compile     # type-check and build to out/
npm test            # compile, then run the parser test suite
```

Press `F5` in VS Code to launch an Extension Development Host with the
extension loaded.

The parsing logic in `src/pythonParser.ts` and `src/braceParser.ts` deliberately
does not import the `vscode` module, so it can be unit-tested with plain Node —
`test/run.ts` exercises it directly without needing an editor instance.

## License

MIT
