# The README and API documentation

Read this when writing or fixing a README, or when documenting a public API
surface with docstrings or doc comments.

## The README

The README is read by someone deciding, in about ten seconds, whether this
repository is relevant to them — and then, if it is, trying to run it. Optimise
the first screen for exactly that.

**Required, in this order:**

1. **Name and one sentence** saying what it does and for whom. Not "a project
   for managing things" — "a CLI that syncs Postgres tables into BigQuery on a
   schedule."
2. **Status badges** if CI exists — build, coverage, version. They answer "is
   this alive" instantly.
3. **Quick start**: the shortest path from clone to running, as commands that
   can be copy-pasted and that actually work in that order. This is the single
   most valuable section in the file.
4. **Requirements**: language version, and every service (database, queue,
   credentials) needed. Discovering the fourth prerequisite by hitting an error
   is the most common newcomer experience, and it is entirely avoidable.
5. **Configuration**: a table of every environment variable — name, required,
   default, description — kept in sync with `.env.example`.
6. **How to run the tests.** One command. Its absence is why contributors submit
   untested changes.
7. **Project layout**: one line per top-level directory, so a reader can
   navigate without opening files.
8. **License**, and where to get help.

Then stop. Deep usage, architecture, and tutorials belong in `docs/`, linked
from here. A README that scrolls for ten screens is one nobody reads to the end
of.

**The rules that keep a README true:**

- **Every command must actually run**, in the order given, from a clean clone.
  Run them. A README whose first command fails destroys trust in the rest of the
  file.
- Write for someone who has never used the project: no internal jargon, no
  team-specific acronyms, no "just" (it is never just).
- Show real commands with real values, not `<PLACEHOLDER>` where a working
  example is possible.
- If setup genuinely takes more than a handful of steps, that is a signal to
  fix the setup — a script, a Makefile, a devcontainer — not to write longer
  instructions.

`assets/README-template.md` is a fill-in skeleton with the sections in order.

## API documentation and docstrings

Document the public surface. Private helpers get a comment only when
non-obvious — documenting everything trains readers to skip all of it.

A doc comment states what the function does, what the parameters mean (including
units and valid ranges the type cannot express), what it returns, what it
raises, and any non-obvious behaviour: side effects, cost, thread-safety,
idempotency.

```py
def charge(order: Order, *, idempotency_key: str) -> Charge:
    """Charge the customer for an order.

    Args:
        order: Must be in PENDING state; charging any other state is an error.
        idempotency_key: Retries with the same key return the original charge
            rather than charging twice. Callers must reuse the key on retry.

    Returns:
        The completed Charge, including the gateway's transaction id.

    Raises:
        CardDeclined: The gateway rejected the card. Not retryable.
        GatewayUnavailable: Transient; safe to retry with the same key.
    """
```

Notice what the annotations could not say: the state precondition, the retry
contract, and which failure is retryable. **That is what a doc comment is for.**
Restating the type signature in prose adds nothing and rots.

Per-language conventions: Google or NumPy style docstrings (Python — pick one
and be consistent), TSDoc (`@param`, `@returns`, `@throws`), godoc (a complete
sentence starting with the identifier's name), rustdoc (`///`, with examples that
are compiled and run as tests), Javadoc/KDoc.

**Prefer documentation the toolchain checks.** Rust doc tests, Python doctests,
and compiled examples cannot silently go stale, because CI fails when they do.
That property is worth more than better prose.
