"""A semantic taxonomy of coding requests, used to bootstrap the dataset.

The point of this file is not to enumerate prompts. It is to cover the
*meaning space* densely enough that an embedding model learns which requests
are hard, rather than which words are present -- which is exactly the failure
mode of the regex lexicon this is meant to replace.

Two structures do that work:

* ARCHETYPES give many surface forms per underlying task shape, so phrasing
  varies while the label does not;
* CONTRASTS give minimal pairs -- near-identical wording, different tier --
  so surface overlap actively *hurts* a keyword matcher and only a model that
  reads the whole sentence can separate them.

Seed data teaches the taxonomy, not your traffic. It is train-only by
construction (see schema.TRAIN_ONLY) and exists to get a usable model before
you have logs, not to be the dataset.
"""

from __future__ import annotations

from dataclasses import dataclass

SLOTS: dict[str, tuple[str, ...]] = {
    "file": ("src/app.py", "lib/parser.ts", "internal/queue.go", "app/models.rb",
             "cmd/serve/main.go", "src/hooks/useAuth.tsx", "pkg/cache/store.go",
             "tests/test_client.py", "config/settings.py", "src/db/session.py"),
    "func": ("parse_config", "handleRequest", "buildIndex", "normalise_path",
             "retryWithBackoff", "load_manifest", "flushBuffer", "resolve_ref"),
    "sym": ("User", "OrderService", "CacheKey", "SessionStore", "Invoice"),
    "cmd": ("the test suite", "the linter", "the build", "the migrations",
            "the type checker", "the formatter"),
    "sub": ("the auth layer", "the job queue", "the caching layer", "the CLI",
            "the export pipeline", "the webhook handler", "the search index",
            "the rate limiter", "the session store", "the billing module"),
    "thing": ("a --json flag", "a --dry-run flag", "pagination", "a retry",
              "input validation", "a health check", "structured logging",
              "a timeout", "an ETag header", "a feature flag"),
}


@dataclass(frozen=True)
class Archetype:
    name: str
    tier: str
    templates: tuple[str, ...]
    why: str


ARCHETYPES: tuple[Archetype, ...] = (
    # ---------------------------------------------------------------- haiku
    Archetype("read_file", "haiku", (
        "read {file} and tell me what it does",
        "open {file} and summarise it",
        "what's in {file}?",
        "show me {file}",
        "give me a quick overview of {file}",
    ), "retrieval and restatement, no judgement"),
    Archetype("explain_symbol", "haiku", (
        "what does {func} do?",
        "explain {func} in {file}",
        "walk me through {func}",
        "what is {sym} used for?",
    ), "explaining code already in front of it"),
    Archetype("locate", "haiku", (
        "where is {func} defined?",
        "find all callers of {func}",
        "which file has {sym} in it?",
        "grep for {func}",
        "list the files under src/",
    ), "search, no synthesis"),
    Archetype("rename", "haiku", (
        "rename {func} to {func}_v2 in {file}",
        "rename the {sym} class to {sym}Record in {file}",
        "change the variable name in {func} to something clearer",
    ), "mechanical, single file, no design"),
    Archetype("format_lint", "haiku", (
        "run {cmd}",
        "run {cmd} and tell me what it says",
        "format {file}",
        "fix the lint errors in {file}",
        "sort the imports in {file}",
    ), "run a command, report output"),
    Archetype("tiny_edit", "haiku", (
        "add a docstring to {func}",
        "add a comment explaining what {func} returns",
        "add a debug log line at the top of {func}",
        "fix the typo in the error message in {file}",
        "bump the version in pyproject.toml",
        "update the changelog for this release",
    ), "one-line change, no ambiguity"),
    Archetype("mechanical_move", "haiku", (
        "move {func} from {file} into a helpers module",
        "delete the unused import in {file}",
        "extract the magic number in {func} into a constant",
    ), "refactor with one obvious right answer"),

    # --------------------------------------------------------------- sonnet
    Archetype("small_feature", "sonnet", (
        "add {thing} to {sub}",
        "wire {thing} into {sub}",
        "implement {thing} for the export command",
        "add {thing} and make sure the existing tests still pass",
    ), "ordinary feature work, approach is clear"),
    Archetype("write_test", "sonnet", (
        "write tests for {func}",
        "add test coverage for {sub}",
        "write a unit test that covers the error path in {func}",
        "add a regression test for the bug we just fixed",
    ), "contained, known target"),
    Archetype("known_bug", "sonnet", (
        "fix the off-by-one in {func}",
        "{func} returns None when the list is empty, fix it",
        "the CLI crashes on an empty config file, handle that",
        "{func} doesn't handle unicode, fix it",
    ), "the fault is already identified"),
    Archetype("contained_refactor", "sonnet", (
        "split {func} into two smaller functions",
        "pull the validation in {file} into its own function",
        "replace the nested ifs in {func} with early returns",
        "convert {func} to use the new client",
    ), "local restructuring, no cross-cutting decisions"),
    Archetype("wire_existing", "sonnet", (
        "hook {sub} up to the metrics collector",
        "make {sub} read its config from the environment",
        "add {sub} to the docker compose file and wire the env vars",
    ), "connecting pieces that already exist"),
    Archetype("adapt_existing", "sonnet", (
        "make {func} handle the empty case as well",
        "extend {func} to accept a list as well as a single value",
        "add an optional {thing} parameter to {func}",
        "make {sub} configurable instead of hardcoded",
        "port {func} to the new API surface",
    ), "clear extension of code that already exists"),
    Archetype("bulk_mechanical", "sonnet", (
        "add type hints across {file}",
        "convert the callbacks in {file} to async/await",
        "replace the deprecated calls in {file} with the new ones",
        "update every call site of {func} for the new signature",
    ), "repetitive, but needs care across a whole file"),
    Archetype("scaffold", "sonnet", (
        "set up pytest with a conftest and one smoke test",
        "add a Dockerfile for this service",
        "add a CI workflow that lints and tests on push",
        "add pre-commit hooks for the formatter and linter",
    ), "routine setup with a known shape"),
    Archetype("docs_from_code", "sonnet", (
        "write a README for {sub}",
        "document the public API of {sub}",
        "write the CONTRIBUTING guide for this repo",
    ), "synthesis, but low risk if imperfect"),

    # ----------------------------------------------------------------- opus
    Archetype("design", "opus", (
        "design {sub} for this service",
        "how should we structure {sub}?",
        "propose an architecture for {sub} and explain the trade-offs",
        "what's the right data model for {sub}?",
        "should {sub} be its own service or stay in the monolith?",
    ), "a wrong approach is expensive to undo"),
    Archetype("mystery_bug", "opus", (
        "why does {sub} intermittently fail in CI but never locally?",
        "we're seeing occasional 500s from {sub} and can't reproduce it",
        "{func} sometimes returns stale data, figure out why",
        "the test suite passes alone but fails when run in parallel, why?",
        "memory grows unbounded in {sub} over a few hours, find the leak",
    ), "the fault is not yet identified"),
    Archetype("concurrency", "opus", (
        "there's a race condition in {sub}, find and fix it",
        "{sub} deadlocks under concurrent load",
        "make {sub} thread-safe without tanking throughput",
        "is {func} safe to call from multiple goroutines?",
    ), "correctness under interleaving; reasoning-heavy"),
    Archetype("migration", "opus", (
        "migrate {sub} from the old schema to the new one without downtime",
        "plan the migration off the deprecated client across the codebase",
        "we need to change the primary key type on the orders table, plan it",
        "upgrade the framework major version across the repo",
    ), "broad blast radius, hard to reverse"),
    Archetype("performance", "opus", (
        "{sub} got 3x slower after the last release, find out why",
        "profile {sub} and cut the p99 latency in half",
        "the endpoint does N+1 queries somewhere, track it down",
        "reduce the memory footprint of {sub} without changing the API",
    ), "needs measurement and judgement, not a known fix"),
    Archetype("security", "opus", (
        "review {sub} for security issues",
        "is our token handling in {sub} safe?",
        "audit the permission checks across {sub}",
        "we might have an IDOR in {sub}, check",
    ), "cost of a miss is high"),
    Archetype("cross_cutting", "opus", (
        "add structured logging across the whole codebase consistently",
        "introduce a Result type and adopt it everywhere errors are returned",
        "standardise error handling across every module",
        "rework how config flows through the entire application",
    ), "touches everything; consistency decisions"),
    Archetype("ambiguous_ask", "opus", (
        "clean this up",
        "make this better",
        "something feels off about {sub}, take a look",
        "this doesn't feel right, can you have a look and fix whatever's wrong?",
        "review my changes and tell me what I've missed",
    ), "underspecified: needs judgement about what 'correct' means"),
)


# Minimal pairs: heavy surface overlap, different tier. These are the rows that
# punish a keyword matcher and reward a model that reads the sentence.
#
# Entries are (cheap_template, cheap_tier, harder_template, harder_tier, shared).
# All three tier boundaries need pairs: an early version of this file only had
# haiku/opus pairs, and the resulting classifier separated "hard" from "not
# hard" cleanly while confusing haiku with sonnet almost at chance.
CONTRASTS: tuple[tuple[str, str, str, str, str], ...] = (
    ("read {file} and summarise it",
     "haiku",
     "read {file} and work out why production diverges from staging",
     "opus", "read"),
    ("rename {sym} to {sym}Record in {file}",
     "haiku",
     "rename {sym} to {sym}Record everywhere and keep the public API backwards compatible",
     "opus", "rename"),
    ("add a test for {func}",
     "haiku",
     "add a test that reliably reproduces the intermittent failure in {func}",
     "opus", "add a test"),
    ("run {cmd}",
     "haiku",
     "run {cmd} and work out why it only fails on CI",
     "opus", "run"),
    ("fix the lint errors in {file}",
     "haiku",
     "fix the flaky test in {file} -- it fails maybe one run in twenty",
     "opus", "fix"),
    ("add {thing} to {sub}",
     "haiku",
     "add {thing} to {sub} without breaking any existing callers, and decide where it belongs",
     "opus", "add"),
    ("what does {func} do?",
     "haiku",
     "what does {func} do that makes it slow, and what would you change?",
     "opus", "what does"),
    ("update the changelog",
     "haiku",
     "update the changelog and decide what deserves a major version bump",
     "opus", "update the changelog"),
    ("move {func} into a helpers module",
     "haiku",
     "move {func} somewhere sensible -- decide what the module boundary should be",
     "opus", "move"),
    ("document the public API of {sub}",
     "haiku",
     "document the public API of {sub} and flag anything we should deprecate before 1.0",
     "opus", "document"),
    ("delete the unused import in {file}",
     "haiku",
     "delete the dead code across the repo -- work out what's genuinely unreachable",
     "opus", "delete"),
    ("format {file}",
     "haiku",
     "reformat the whole repo and pick the style rules we should standardise on",
     "opus", "format"),
    ("add input validation to {func}",
     "haiku",
     "add input validation everywhere untrusted data enters the system",
     "opus", "add input validation"),
    ("write a unit test for {func}",
     "haiku",
     "design the test strategy for {sub} -- what should be unit vs integration?",
     "opus", "test"),
    ("show me {file}",
     "haiku",
     "show me why {sub} behaves differently under load",
     "opus", "show me"),
    ("fix the off-by-one in {func}",
     "haiku",
     "fix whatever is corrupting the index -- we know the symptom, not the cause",
     "opus", "fix"),
    ("add a retry to {func}",
     "haiku",
     "design the retry and backoff policy for {sub}, including the failure modes",
     "opus", "retry"),
    ("bump the version",
     "haiku",
     "plan the release: version, migration notes, and the deprecation window",
     "opus", "version"),
    ("add a timeout to the HTTP client",
     "haiku",
     "work out why requests hang past the timeout and fix the root cause",
     "opus", "timeout"),
    ("list the files under src/",
     "haiku",
     "map the dependency graph under src/ and tell me where the cycles are",
     "opus", "src/"),

    # haiku vs sonnet -- "mechanical" against "needs a little judgement". This is
    # the boundary a keyword matcher gets most wrong, because both sides reach
    # for the same verbs.
    ("add a docstring to {func}",
     "haiku",
     "add docstrings to every public method in {file}, matching the house style",
     "sonnet", "docstring"),
    ("add httpx to the requirements file",
     "haiku",
     "swap requests for httpx in {file} and update the call sites",
     "sonnet", "dependency"),
    ("change the timeout to 30s in {file}",
     "haiku",
     "make the timeout configurable per environment",
     "sonnet", "timeout"),
    ("run {cmd}",
     "haiku",
     "run {cmd} and fix whatever it reports",
     "sonnet", "run"),
    ("what does {func} return?",
     "haiku",
     "make {func} return a typed result instead of a dict",
     "sonnet", "return"),
    ("remove the unused variable in {func}",
     "haiku",
     "remove the dead branch in {func} and add a test proving it is unreachable",
     "sonnet", "remove"),
    ("add a log line when {func} starts",
     "haiku",
     "add structured logging to {sub} with request ids",
     "sonnet", "logging"),
    ("show me the tests for {func}",
     "haiku",
     "write the missing tests for {func}, including the error paths",
     "sonnet", "tests"),
    ("fix the typo in the error message",
     "haiku",
     "make the error messages in {sub} consistent and actionable",
     "sonnet", "error message"),
    ("add the new field to the fixture",
     "haiku",
     "add the new field end to end: model, serialiser, migration and tests",
     "sonnet", "add the new field"),
    ("rename {func} in {file}",
     "haiku",
     "rename {func} and update every call site in the package",
     "sonnet", "rename"),
    ("copy the config template",
     "haiku",
     "add a second config profile and make the loader pick between them",
     "sonnet", "config"),

    # sonnet vs opus -- "the approach is clear" against "the approach is the problem".
    ("fix the off-by-one in {func}",
     "sonnet",
     "fix whatever makes {func} return different results on repeat runs",
     "opus", "fix"),
    ("add a retry to the http client",
     "sonnet",
     "work out the right retry and timeout budget for {sub} end to end",
     "opus", "retry"),
    ("write tests for {func}",
     "sonnet",
     "work out why the tests for {func} pass alone and fail in the suite",
     "opus", "tests"),
    ("add caching to {func}",
     "sonnet",
     "decide what in {sub} is safe to cache and for how long",
     "opus", "caching"),
    ("add pagination to the list endpoint",
     "sonnet",
     "our pagination skips rows when data changes mid-scroll, fix it properly",
     "opus", "pagination"),
    ("add validation to the signup form",
     "sonnet",
     "audit every place untrusted input reaches the database",
     "opus", "validation"),
    ("split {func} into smaller functions",
     "sonnet",
     "the module boundaries in {sub} are wrong, propose a better split",
     "opus", "split"),
    ("write a migration to add a column",
     "sonnet",
     "write the migration and the rollout plan so we can deploy without downtime",
     "opus", "migration"),
    ("make the logger emit json",
     "sonnet",
     "our logs are unusable during incidents, work out what we should change",
     "opus", "logs"),
    ("add a health check endpoint",
     "sonnet",
     "design how this service should report readiness vs liveness under partial failure",
     "opus", "health"),

)


# Requests that arrive mid-task, where the loop position matters more than the
# words. Generated with a synthetic conversation context in seed.py.
FOLLOWUPS: tuple[tuple[str, str], ...] = (
    ("haiku", "now summarise what you found"),
    ("haiku", "ok, apply that change"),
    ("haiku", "show me the diff"),
    ("haiku", "just the file list please"),
    ("sonnet", "now make the same change in the other two files"),
    ("sonnet", "good, now add a test for it"),
    ("opus", "that didn't work -- try something else"),
    ("opus", "still failing, dig deeper"),
    ("opus", "no, that's the wrong approach entirely"),
    ("opus", "it's still flaky after that fix"),
)


# Surface variation applied on top of templates so phrasing is not a shortcut.
PREFIXES: tuple[str, ...] = (
    "", "", "", "please ", "can you ", "hey, ", "quick one: ", "I need you to ",
    "when you get a chance, ", "could you ",
)

SUFFIXES: tuple[str, ...] = (
    "", "", "", "", " thanks", " -- keep it minimal", " when you can",
    " (no rush)", ". let me know what you find",
)
