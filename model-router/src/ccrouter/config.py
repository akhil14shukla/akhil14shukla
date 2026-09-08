"""Configuration loading and the tier vocabulary the whole router speaks."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, replace  # noqa: F401  (re-exported for the CLI)
from pathlib import Path
from typing import Any

TIER_NAMES = ("haiku", "sonnet", "opus")

HAIKU, SONNET, OPUS = 0, 1, 2


def tier_index(name: str) -> int:
    try:
        return TIER_NAMES.index(name.strip().lower())
    except ValueError:
        raise ValueError(f"unknown tier {name!r}, expected one of {TIER_NAMES}") from None


def tier_name(index: int) -> str:
    return TIER_NAMES[max(0, min(len(TIER_NAMES) - 1, index))]


DEFAULT_CHEAP_LEXICON = [
    r"\bread (the |this )?file\b", r"\bshow me\b", r"\bcat\b", r"\bprint\b",
    r"\blist (the |all )?(files|directories|functions|tests)\b", r"\bwhere is\b",
    r"\bwhat does .{0,40} do\b", r"\bfind the\b", r"\bgrep\b", r"\bsummari[sz]e\b",
    r"\brename\b", r"\btypo\b", r"\bformat (this|the)\b", r"\brun (the )?(tests|linter|formatter)\b",
    r"\badd a (log|comment|docstring|print)\b", r"\bbump (the )?version\b",
    r"\bupdate the (changelog|readme)\b", r"\bwhat is (in|the)\b", r"\bhow many\b",
    r"\bcopy\b", r"\bmove (the )?file\b", r"\bdelete (the )?(file|line)\b",
]

DEFAULT_EXPENSIVE_LEXICON = [
    r"\bdesign\b", r"\barchitect(ure)?\b", r"\brefactor\b", r"\bmigrat(e|ion)\b",
    r"\brace condition\b", r"\bdead ?lock\b", r"\bconcurren(cy|t)\b", r"\bthread[- ]safe\b",
    r"\bwhy (is|does|are|did)\b", r"\broot cause\b", r"\bdebug\b", r"\bintermittent\b",
    r"\bflaky\b", r"\boptimi[sz]e\b", r"\bperformance\b", r"\bbottleneck\b",
    r"\bsecurity\b", r"\bvulnerab(le|ility)\b", r"\bauth(entication|orization)\b",
    r"\btrade[- ]?offs?\b", r"\bpros and cons\b", r"\bevaluate\b", r"\bcompare approaches\b",
    r"\bredesign\b", r"\bschema (change|migration)\b", r"\bbackwards[- ]compatib\w+\b",
    r"\bdistributed\b", r"\bconsistency\b", r"\balgorithm\b", r"\bcomplexity\b",
    r"\bplan\b", r"\bstrategy\b", r"\bend[- ]to[- ]end\b",
]

# Tools that only observe. A turn that used nothing else is a recall/summarise step.
DEFAULT_READONLY_TOOLS = [
    "Read", "Glob", "Grep", "NotebookRead", "WebFetch", "WebSearch",
    "TodoRead", "ListMcpResourcesTool", "ReadMcpResourceTool",
]

DEFAULT_FAILURE_PATTERNS = [
    r"Traceback \(most recent call last\)", r"\berror TS\d+\b", r"\bFAILED\b",
    r"\bAssertionError\b", r"\bSyntaxError\b", r"\bTypeError\b", r"\bpanic:",
    r"npm ERR!", r"\bexit (code|status) [1-9]", r"\bSegmentation fault\b",
    r"\b\d+ (test(s)? )?failed\b", r"\bfatal:", r"\bcommand not found\b",
    r"\bModuleNotFoundError\b", r"\bcompilation failed\b", r"\bE\d{3}\b",
]

DEFAULT_WEIGHTS: dict[str, float] = {
    "cheap_intent": -0.35,
    "expensive_intent": 0.35,
    "short_question": -0.20,
    "single_file_edit": -0.25,
    "broad_scope": 0.30,
    "multi_file": 0.25,
    "multi_step": 0.20,
    "pasted_stacktrace": 0.30,
    "underspecified": 0.15,
    "long_instruction": 0.20,
    "thinking_enabled": 0.40,
    "readonly_followup": -0.50,
    "mutating_followup": 0.10,
    "recent_failures": 0.25,
    "tool_thrash": 0.30,
    "large_context": 0.15,
    "cheap_subagent": -0.60,
}


@dataclass(frozen=True)
class LLMConfig:
    enabled: bool = False
    endpoint: str = "http://localhost:11434/v1/chat/completions"
    model: str = "qwen2.5:3b"
    api_key_env: str = ""
    timeout_s: float = 2.5
    dead_band: float = 0.18
    prompt_file: str = ""
    cache_size: int = 512


@dataclass(frozen=True)
class SemanticConfig:
    """The learned scorer. Trained by ml/train.py; optional at runtime."""

    enabled: bool = False
    model_path: str = "~/.claude/model-router/model.npz"
    encoder: str = ""              # empty: use whatever the model was trained with
    weight: float = 0.6            # how much the margin can move the score
    min_confidence: float = 0.45   # below this the model abstains


@dataclass(frozen=True)
class Policy:
    default_tier: str = "sonnet"
    min_tier: str = "haiku"
    max_tier: str = "opus"
    cheap_threshold: float = -0.25
    expensive_threshold: float = 0.35
    haiku_context_ceiling_tokens: int = 80_000
    thinking_floor_sonnet_tokens: int = 4_000
    thinking_floor_opus_tokens: int = 24_000
    failures_floor_sonnet: int = 2
    failures_floor_opus: int = 4
    sticky_turns: bool = True
    allow_mid_turn_downgrade: bool = False
    passthrough_background: bool = True
    cheap_agents: tuple[str, ...] = ("explore", "search", "statusline-setup")

    # Fraction of fresh human turns routed to a neighbouring tier at random.
    # Costs a little accuracy and buys the only unbiased training data you can
    # get: outcomes for tiers the policy would not otherwise have chosen.
    explore_rate: float = 0.0


@dataclass(frozen=True)
class Config:
    listen: str = "127.0.0.1:4000"
    upstream: str = "https://api.anthropic.com"
    log_file: str = "~/.claude/model-router/decisions.jsonl"
    tiers: dict[str, str] = field(
        default_factory=lambda: {
            "haiku": "claude-haiku-4-5-20251001",
            "sonnet": "claude-sonnet-5",
            "opus": "claude-opus-5",
        }
    )
    policy: Policy = field(default_factory=Policy)
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    cheap_lexicon: tuple[str, ...] = tuple(DEFAULT_CHEAP_LEXICON)
    expensive_lexicon: tuple[str, ...] = tuple(DEFAULT_EXPENSIVE_LEXICON)
    readonly_tools: tuple[str, ...] = tuple(DEFAULT_READONLY_TOOLS)
    failure_patterns: tuple[str, ...] = tuple(DEFAULT_FAILURE_PATTERNS)
    subagent_markers: tuple[str, ...] = (r"You are an agent for Claude Code",)
    llm: LLMConfig = field(default_factory=LLMConfig)
    semantic: SemanticConfig = field(default_factory=SemanticConfig)
    pricing_per_mtok_in: dict[str, float] = field(
        default_factory=lambda: {"haiku": 1.0, "sonnet": 3.0, "opus": 15.0}
    )

    def model_for(self, tier: int) -> str:
        return self.tiers[tier_name(tier)]

    def tier_of_model(self, model: str) -> int | None:
        """Map a concrete model id back onto a tier, by exact id then by family word."""
        for name, ident in self.tiers.items():
            if ident == model:
                return tier_index(name)
        low = model.lower()
        for name in TIER_NAMES:
            if name in low:
                return tier_index(name)
        return None


def _merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        return {k: _merge(base.get(k), v) if k in base else v for k, v in {**base, **override}.items()}
    return override if override is not None else base


def load(path: str | os.PathLike[str] | None = None) -> Config:
    """Load router.toml, falling back to built-in defaults for anything absent."""
    cfg = Config()
    candidates = [path] if path else [
        os.environ.get("CCROUTER_CONFIG"),
        Path.cwd() / "router.toml",
        Path.home() / ".claude" / "model-router" / "router.toml",
    ]
    raw: dict[str, Any] = {}
    for candidate in candidates:
        if not candidate:
            continue
        p = Path(candidate).expanduser()
        if p.is_file():
            raw = tomllib.loads(p.read_text(encoding="utf-8"))
            break

    if not raw:
        return cfg

    policy = replace(cfg.policy, **{
        k: (tuple(v) if isinstance(v, list) else v)
        for k, v in raw.get("policy", {}).items()
        if k in Policy.__dataclass_fields__
    })
    llm = replace(cfg.llm, **{
        k: v for k, v in raw.get("llm", {}).items() if k in LLMConfig.__dataclass_fields__
    })
    semantic = replace(cfg.semantic, **{
        k: v for k, v in raw.get("semantic", {}).items()
        if k in SemanticConfig.__dataclass_fields__
    })
    lex = raw.get("lexicon", {})

    return replace(
        cfg,
        listen=raw.get("listen", cfg.listen),
        upstream=raw.get("upstream", cfg.upstream).rstrip("/"),
        log_file=raw.get("log_file", cfg.log_file),
        tiers={**cfg.tiers, **raw.get("tiers", {})},
        policy=policy,
        weights={**cfg.weights, **raw.get("weights", {})},
        cheap_lexicon=tuple(lex.get("cheap", cfg.cheap_lexicon)),
        expensive_lexicon=tuple(lex.get("expensive", cfg.expensive_lexicon)),
        readonly_tools=tuple(raw.get("readonly_tools", cfg.readonly_tools)),
        failure_patterns=tuple(raw.get("failure_patterns", cfg.failure_patterns)),
        subagent_markers=tuple(raw.get("subagent_markers", cfg.subagent_markers)),
        llm=llm,
        semantic=semantic,
        pricing_per_mtok_in={**cfg.pricing_per_mtok_in, **raw.get("pricing_per_mtok_in", {})},
    )
