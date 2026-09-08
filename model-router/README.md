# model-router

Routes each Claude Code request to the cheapest model that can do it correctly.
Haiku for reading files and mechanical edits, Sonnet for ordinary feature work,
Opus for design, debugging, and anything ambiguous — decided per request from
the shape of the conversation, not from a token count.

```
$ ccrouter explain "why does the scheduler intermittently deadlock under load?"
contributions
  expensive_intent     +0.70  2 hard phrase(s)
  config_min_tier      floor=haiku  configured floor
score       +0.70  (cheap<=-0.25, opus>=0.35)
DECISION    opus  ->  claude-opus-5   [rules]

$ ccrouter explain "rename the parse function in src/app.py"
contributions
  cheap_intent         -0.26  1 cheap phrase(s)
  single_file_edit     -0.25  one file named, no fan-out
score       -0.51
DECISION    haiku  ->  claude-haiku-4-5-20251001   [rules]
```

## Why a proxy and not a hook

**No hook can change the model.** Every hook event was checked against the
[hooks reference](https://code.claude.com/docs/en/hooks): `UserPromptSubmit`
returns `updatedInput`, `additionalContext` and `systemMessage`, and there is
no `model` field in any event's output schema. `PreModelSwitch` can *block* a
switch but not redirect one. MCP is the wrong layer too — an MCP server hands
tools to a model that has already been chosen.

The one place the model is still a mutable value is the request body on its way
to the API. `ANTHROPIC_BASE_URL` puts a process there, so that is where this
lives: a local reverse proxy that rewrites `body.model` on `/v1/messages` and
relays everything else — headers, credentials, streaming — byte for byte.

The plugin also ships an **advisory hook** for people who would rather not run
a proxy. It can't switch the model, but it runs the same rules and tells Claude
in context when the work is cheap enough to hand to the bundled Haiku subagent.
Weaker, but zero infrastructure.

## Install

Nothing to install — standard library only, Python 3.11+.

```bash
git clone https://github.com/akhil14shukla/akhil14shukla
cd akhil14shukla/model-router
python3 -m unittest discover -s tests          # 45 tests, ~2s

mkdir -p ~/.claude/model-router
cp router.toml.example ~/.claude/model-router/router.toml   # edit the tiers

alias ccrouter='PYTHONPATH=~/path/to/model-router/src python3 -m ccrouter'
```

Then, in one terminal:

```bash
ccrouter serve
#   ccrouter 0.1.0 listening on http://127.0.0.1:4000 -> https://api.anthropic.com
```

and in the one where you run Claude Code:

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:4000
claude
```

To make it permanent, put it in `~/.claude/settings.json`:

```json
{ "env": { "ANTHROPIC_BASE_URL": "http://127.0.0.1:4000" } }
```

As a plugin (for the `/route` command, the advisory hook and the `quick`
subagent), point a marketplace at this repo or copy the directory into
`~/.claude/skills/`. `claude plugin validate .` passes.

## What it routes on

Token count is the weakest available signal, and it is used here only as a
guard rail. The interesting signals are structural — they come from the request
body Claude Code already sends, which carries far more than the prompt text.

**Where you are in the loop.** One human turn produces many API calls. A step
whose previous action was `Read`, `Grep`, `Glob`, or a read-only `Bash` command
is almost always "summarise what you just saw" — that is Haiku work regardless
of how hard the original question was.

**Whether the loop is in trouble.** Failing tool results, `is_error` flags,
stack traces in tool output, and the same tool call repeated with identical
arguments all raise the floor. A model that has failed twice does not get a
third cheap attempt.

**Blast radius.** How many distinct paths the prompt names; whether it contains
a glob or "across the codebase"; whether it enumerates steps. Three files and
four steps is a different job from one file and one verb.

**Intent, from a lexicon you own.** `design`, `race condition`, `why does`,
`migrate`, `trade-offs` push up; `show me`, `rename`, `run the tests`, `bump
the version` push down. Both lists are regexes in the config file.

**Underspecification.** "fix it" names nothing and needs judgement about what
"it" refers to — that is a reason to go *up*, not down, even though the prompt
is three words long.

**Explicit intent from the caller.** Extended thinking sets a floor. `!opus` or
`!haiku` anywhere in the prompt pins the tier outright.

**Who is asking.** Search and explore subagents route cheap. Claude Code's own
background Haiku calls (chat titles, summaries) are passed through untouched
rather than upgraded.

### Scores, floors and pins

Rules contribute one of three things, and keeping them separate is the point:

- a **score** in `[-1.5, +1.5]`, compared against two thresholds;
- a **floor**, which no amount of cheap-looking evidence may undercut;
- a **pin**, which settles the matter (a user override, or the classifier).

Without that split, one strong cheap signal ("summarise this") drags a request
that also has a pasted stack trace and two failing test runs onto the small
model. With it, the floor wins.

### Stickiness: decide once per turn, and only ever ratchet up

This is the part that is easy to leave out and expensive to omit. Re-deciding
on every API call would flip models mid-task — which throws away the prompt
cache on every switch and lets the agent contradict its own earlier reasoning.

So the tier is chosen when a new human turn arrives and pinned for the rest of
that turn. Escalation is the one thing allowed to break the pin: if tool calls
start failing, the router upgrades immediately and **never falls back down**
inside that turn, even when a later step looks trivial in isolation. The next
human message starts fresh.

## Optional: a local LLM as tiebreaker

Rules are decisive at the edges and vague in the middle. When a score lands
within `dead_band` of a threshold — on a fresh human turn, not mid-loop — the
router can ask a small local model to break the tie:

```toml
[llm]
enabled   = true
endpoint  = "http://localhost:11434/v1/chat/completions"   # Ollama, llama.cpp, LM Studio, vLLM
model     = "qwen2.5:3b"
timeout_s = 2.5
dead_band = 0.18
prompt_file = "~/.claude/model-router/classify.md"          # your own prompt
```

Any OpenAI-compatible `/chat/completions` endpoint works. The prompt template
is [`prompts/classify.md`](prompts/classify.md) — copy it, edit it, point
`prompt_file` at yours; `{{PROMPT}}`, `{{RULE_TIER}}`, `{{RULE_SCORE}}` and
`{{SIGNALS}}` are substituted.

It is deliberately hard for this to hurt you. It is skipped entirely when the
rules are confident, answers are cached by prompt hash, the timeout is short,
its answer is clamped to the floors and ceilings the rules established, and any
failure — timeout, connection refused, a chatty answer it can't parse — leaves
the rule verdict standing and says so in the log. `ccrouter doctor` tells you
whether it is actually reachable.

## Seeing what it did

```bash
ccrouter stats
#   412 decisions  (301 rewrote the model)
#     haiku    203 calls    1,204,882 input tok (49.3%)
#     sonnet   171 calls    2,901,004 input tok (41.5%)
#     opus      38 calls      944,120 input tok ( 9.2%)
#     by source: rules=364, sticky=31, escalation=12, passthrough=5
#     estimated saving  $54.312  (68%)
```

Every decision is appended to `~/.claude/model-router/decisions.jsonl` with its
score and reasons. Responses carry `x-ccrouter-tier`, `x-ccrouter-source` and
`x-ccrouter-from` headers, and the proxy serves `/__router/stats` and
`/__router/healthz`.

Cost figures are estimates from request bodies at 4 chars/token, input tokens
only — good enough to compare configurations, not an invoice.

## Tuning it

`ccrouter explain` is the whole feedback loop. Run it on prompts you actually
send, look at which contributions fired, then move a weight or add a phrase:

```bash
ccrouter explain "add a --json flag to the export command"
ccrouter explain --request /tmp/captured-body.json     # a real /v1/messages body
```

If it is too eager to go cheap, raise `cheap_threshold` toward `0`. If Haiku is
getting work it fumbles, add the phrases that fooled it to `lexicon.expensive`.
To cap spend without touching anything else, set `max_tier = "sonnet"`.

## Caveats worth knowing before you rely on it

- **Setting `ANTHROPIC_BASE_URL` changes more than routing.** Per the
  [docs](https://code.claude.com/docs/en/env-vars): MCP tool search is disabled
  for non-first-party hosts unless you set `ENABLE_TOOL_SEARCH=true`, and
  Remote Control is disabled when it points anywhere but `api.anthropic.com`
  (v2.1.196+). Those are the costs of the only working approach.
- **Auth is relayed, not re-issued.** The proxy forwards `x-api-key` /
  `authorization` untouched, so an API key works as-is. It should also work on
  a Pro/Max subscription, but Anthropic does not document subscription auth
  through a custom base URL — verify it on your own account before depending
  on it.
- **The `/model` display will lie.** Claude Code shows the model it *asked*
  for; the rewrite happens after that. `x-ccrouter-tier` and the decision log
  are the truth.
- **Anything unexpected fails open.** A body it can't parse, a routing
  exception, a dead classifier — the original request goes upstream unchanged.
  An unreachable upstream returns an API-shaped 502 rather than a bare socket
  error.
- **Downgrading is a real quality trade.** The floors exist because a retry on
  a stronger model costs more than the upgrade would have. Start with
  `min_tier = "sonnet"` for a week if you want to watch the decisions before
  trusting them.
- **Cross-model prompt caching does not transfer.** Stickiness limits switches
  to roughly one per human turn; if your cache hit rate drops more than you
  expected, that is the first thing to look at.

## Layout

```
model-router/
├── src/ccrouter/
│   ├── signals.py      request body -> features (the conversation's shape)
│   ├── rules.py        features -> scored, floored, explained verdict
│   ├── classifier.py   optional local-LLM tiebreaker, fail-open
│   ├── router.py       turn stickiness, escalation ratchet, decision log
│   ├── proxy.py        the ANTHROPIC_BASE_URL reverse proxy
│   └── cli.py          serve / explain / stats / doctor
├── hooks/advise.py     UserPromptSubmit advisory mode (no proxy needed)
├── agents/quick.md     Haiku subagent the advisory hook delegates to
├── prompts/classify.md the editable classifier prompt
└── tests/              45 tests, stdlib unittest, real sockets
```
