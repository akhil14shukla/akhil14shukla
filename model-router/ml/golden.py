"""A hand-labelled test set. The only honest number in the pipeline comes from here.

These prompts are deliberately unlike the taxonomy in `taxonomy.py`: different
vocabulary, real-world messiness, lowercase, typos, references to context the
model cannot see. If a classifier trained on seed data scores well *here*, it
generalised. If it only scores well on held-out seed rows, it memorised a
template set.

**These labels are one person's judgement.** They encode a particular tolerance
for risk -- notably that an underspecified request is expensive, not cheap.
Re-label them against your own traffic before trusting the score; that is the
single highest-value hour you can spend on this pipeline.

    python3 ml/golden.py --out ml/dataset/golden.jsonl
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from schema import Example, describe, write

# (prompt, tier, why)
GOLDEN: tuple[tuple[str, str, str], ...] = (
    # ------------------------------------------------------------- haiku
    ("whats in the makefile", "haiku", "read one file"),
    ("cat the dockerfile for me", "haiku", "read one file"),
    ("show me the last 30 lines of the server log", "haiku", "read, no analysis"),
    ("which version of react are we on?", "haiku", "lookup"),
    ("add a TODO comment above the retry loop", "haiku", "one-line edit"),
    ("run npm test", "haiku", "run and report"),
    ("what's the default timeout set to?", "haiku", "lookup"),
    ("list the env vars this service reads", "haiku", "enumerate"),
    ("fix the spelling mistake in the CLI help text", "haiku", "trivial edit"),
    ("add type hints to get_user", "haiku", "mechanical, one function"),
    ("remove the stray console.log in App.tsx", "haiku", "trivial edit"),
    ("what does this regex match? ^[a-z0-9_-]{3,16}$", "haiku", "explain in place"),
    ("rename the test file so it matches the module name", "haiku", "mechanical"),
    ("add httpx to requirements.txt", "haiku", "trivial edit"),
    ("show me the users table schema", "haiku", "read"),
    ("how many lines is src/server.ts", "haiku", "count"),
    ("reformat this json blob so i can read it", "haiku", "format"),
    ("change the port to 8080 in docker-compose", "haiku", "one-value edit"),
    ("which tests are currently skipped?", "haiku", "search"),
    ("print the git log for the last 5 commits", "haiku", "run and report"),
    ("what are the exported functions in utils.ts", "haiku", "enumerate"),
    ("add a trailing newline to the config file", "haiku", "trivial"),
    ("copy the example env file to .env", "haiku", "mechanical"),
    ("tell me what the build script does", "haiku", "read and restate"),
    ("uppercase the header keys in the fixture", "haiku", "mechanical"),

    # ------------------------------------------------------------ sonnet
    ("add a --verbose flag to the cli and thread it through to the logger", "sonnet",
     "small feature, clear approach"),
    ("write tests for the pagination helper", "sonnet", "contained test writing"),
    ("the date parser breaks on ISO strings ending in Z, fix it", "sonnet",
     "fault already identified"),
    ("add retry with exponential backoff to the http client", "sonnet",
     "known pattern, contained"),
    ("convert these classes to dataclasses", "sonnet", "mechanical but multi-step"),
    ("add a POST /orders endpoint following the same pattern as /users", "sonnet",
     "template exists"),
    ("cache get_config in memory so we stop re-reading the file", "sonnet",
     "small, clear"),
    ("the form doesn't clear after submit, fix it", "sonnet", "narrow, reproducible"),
    ("this function is 300 lines, split it up sensibly", "sonnet", "local refactor"),
    ("add validation so we reject negative quantities", "sonnet", "contained"),
    ("write a migration adding a nullable email column", "sonnet", "routine"),
    ("make the logger emit json when ENV=production", "sonnet", "small feature"),
    ("add a /ready endpoint that returns 200", "sonnet", "routine"),
    ("wire the new settings module into the app factory", "sonnet", "connect existing"),
    ("parametrise these three near-identical tests", "sonnet", "local test refactor"),
    ("add pagination to the list endpoint, 50 per page", "sonnet", "spec is given"),
    ("the CLI should exit non-zero when validation fails", "sonnet", "narrow"),
    ("write a docstring for every public method in this module", "sonnet",
     "bulk but mechanical"),
    ("add a dry-run mode to the sync command", "sonnet", "contained feature"),
    ("stub out the payment client so the tests don't hit the network", "sonnet",
     "routine test work"),
    ("update the README to cover the new install steps", "sonnet", "synthesis, low risk"),
    ("add a github action that runs the test suite on push", "sonnet", "routine config"),

    # -------------------------------------------------------------- opus
    ("users are occasionally seeing someone else's data, figure out what's going on",
     "opus", "correctness + security, cause unknown"),
    ("p99 latency doubled after friday's deploy and i can't see why", "opus",
     "regression, cause unknown"),
    ("should we put a queue in front of this or just do it inline?", "opus",
     "architecture decision"),
    ("this test passes locally and fails on CI about a third of the time", "opus",
     "nondeterminism"),
    ("we need to shard this table, walk me through the options", "opus",
     "irreversible design"),
    ("something's wrong with our caching, stale data keeps showing up", "opus",
     "cause unknown"),
    ("review this PR for anything that could bite us in prod", "opus",
     "open-ended judgement"),
    ("i'm not sure this abstraction is right, what do you think?", "opus",
     "design judgement"),
    ("we're getting deadlocks in postgres under load", "opus", "concurrency"),
    ("how do we migrate off this library without a big bang rewrite?", "opus",
     "migration strategy"),
    ("memory keeps climbing overnight and drops when we restart", "opus", "leak hunt"),
    ("make it faster", "opus", "underspecified"),
    ("tidy this up a bit", "opus", "underspecified"),
    ("the numbers in the report don't match the dashboard, work out which is wrong",
     "opus", "cause unknown, correctness"),
    ("design the permissions model for multi-tenant workspaces", "opus",
     "architecture + security"),
    ("we keep getting duplicate webhook deliveries processed twice", "opus",
     "idempotency, distributed"),
    ("is it safe to run two instances of this worker?", "opus", "concurrency reasoning"),
    ("our error rate spikes every day around 3am, no idea why", "opus", "cause unknown"),
    ("refactor the whole data access layer to use the repository pattern", "opus",
     "cross-cutting, hard to reverse"),
    ("something about the way we handle timezones is wrong, users in AU report "
     "the wrong day", "opus", "subtle correctness"),
    ("audit where we log user data and make sure we're not leaking PII", "opus",
     "security, broad"),
    ("the queue backs up under load but CPU is idle, what's the bottleneck?", "opus",
     "performance diagnosis"),
    ("plan how we'd split this monolith, and tell me if we shouldn't", "opus",
     "architecture, includes 'should we'"),
    ("we're hitting a rate limit somewhere but i can't tell which call", "opus",
     "diagnosis"),
    ("this works but it feels fragile -- what would you change?", "opus",
     "open-ended judgement"),
)


def build() -> list[Example]:
    return [
        Example(prompt=prompt, label=tier, source="golden", label_source="human",
                weight=1.0, rationale=why, signals={"phase": "user_turn"})
        for prompt, tier, why in GOLDEN
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="ml/dataset/golden.jsonl")
    args = parser.parse_args(argv)
    rows = build()
    write(args.out, rows)
    print(f"wrote {args.out}")
    print(describe(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
