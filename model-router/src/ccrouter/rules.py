"""The rule engine: signals in, an explained tier out.

Rules contribute one of three things:

* a **score** in roughly [-1, +1] -- negative means "cheaper is fine",
  positive means "this needs a stronger model";
* a **floor**, which no amount of cheap-looking evidence may undercut;
* a **pin**, which settles the decision outright.

Keeping floors separate from scores is what stops one strong cheap signal
("summarise this") from dragging a request with a pasted stack trace and two
failing test runs down onto the small model.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import HAIKU, OPUS, SONNET, Config, tier_index, tier_name
from .signals import Signals


@dataclass(frozen=True)
class Contribution:
    rule: str
    kind: str          # "score" | "floor" | "ceiling" | "pin"
    value: float | int
    detail: str = ""

    def describe(self) -> str:
        if self.kind == "score":
            return f"{self.rule:<20} {self.value:+.2f}  {self.detail}"
        return f"{self.rule:<20} {self.kind}={tier_name(int(self.value))}  {self.detail}"


@dataclass
class Verdict:
    tier: int
    score: float
    contributions: list[Contribution] = field(default_factory=list)
    source: str = "rules"          # rules | override | llm | sticky | passthrough
    confident: bool = True

    @property
    def reasons(self) -> list[str]:
        return [c.describe() for c in self.contributions]


def _score_rules(s: Signals, cfg: Config) -> list[Contribution]:
    w = cfg.weights
    out: list[Contribution] = []

    def add(rule: str, factor: float = 1.0, detail: str = "") -> None:
        value = w.get(rule, 0.0) * factor
        if value:
            out.append(Contribution(rule, "score", value, detail))

    # -- What the human actually asked for -------------------------------
    if s.matched_cheap:
        # Diminishing returns: three cheap phrases are not three times as cheap.
        add("cheap_intent", min(len(s.matched_cheap), 2) * 0.75,
            f"{len(s.matched_cheap)} cheap phrase(s)")
    if s.matched_expensive:
        add("expensive_intent", min(len(s.matched_expensive), 2),
            f"{len(s.matched_expensive)} hard phrase(s)")
    if s.is_question and s.prompt_chars < 200 and not s.matched_expensive:
        add("short_question", detail="short question about existing code")
    if s.files_mentioned == 1 and not s.broad_scope and s.enumerated_steps == 0:
        add("single_file_edit", detail="one file named, no fan-out")

    # -- Blast radius ----------------------------------------------------
    if s.broad_scope:
        add("broad_scope", detail="glob or whole-codebase wording")
    if s.files_mentioned >= 3:
        add("multi_file", detail=f"{s.files_mentioned} paths named")
    if s.enumerated_steps >= 3:
        add("multi_step", detail=f"{s.enumerated_steps} steps")
    if s.prompt_chars > 1200:
        add("long_instruction", detail=f"{s.prompt_chars} chars of instruction")

    # -- Evidence that this is already hard -------------------------------
    if s.has_stacktrace:
        add("pasted_stacktrace", detail="stack trace / compiler error in prompt")
    if s.failures:
        add("recent_failures", min(s.failures, 3), f"{s.failures} failing tool result(s)")
    if s.thrash >= 2:
        add("tool_thrash", detail=f"same tool call repeated {s.thrash}x")

    # -- Underspecified work needs judgement, not just speed --------------
    if s.underspecified:
        add("underspecified", detail="refers to prior context without naming it")

    # -- Where we are in the agentic loop ---------------------------------
    if s.phase == "tool_loop":
        if s.recent_tools_readonly and not s.failures:
            add("readonly_followup", detail=f"last step only read: {', '.join(s.recent_tools[:4])}")
        elif any(t in ("Edit", "Write", "NotebookEdit", "MultiEdit") for t in s.recent_tools):
            add("mutating_followup", detail="mid-edit")

    if s.thinking_budget:
        add("thinking_enabled", detail=f"budget {s.thinking_budget}")
    if s.context_tokens > cfg.policy.haiku_context_ceiling_tokens:
        add("large_context", detail=f"~{s.context_tokens} tok of context")
    if s.is_subagent and s.agent_hint in cfg.policy.cheap_agents:
        add("cheap_subagent", detail=f"{s.agent_hint} subagent")

    return out


def _floor_rules(s: Signals, cfg: Config) -> list[Contribution]:
    p = cfg.policy
    out = [Contribution("config_min_tier", "floor", tier_index(p.min_tier), "configured floor")]

    if s.thinking_budget >= p.thinking_floor_opus_tokens:
        out.append(Contribution("thinking_budget", "floor", OPUS,
                                f"budget {s.thinking_budget} >= {p.thinking_floor_opus_tokens}"))
    elif s.thinking_budget >= p.thinking_floor_sonnet_tokens:
        out.append(Contribution("thinking_budget", "floor", SONNET,
                                f"budget {s.thinking_budget} >= {p.thinking_floor_sonnet_tokens}"))

    if s.failures >= p.failures_floor_opus:
        out.append(Contribution("stuck_loop", "floor", OPUS, f"{s.failures} failures"))
    elif s.failures >= p.failures_floor_sonnet:
        out.append(Contribution("struggling", "floor", SONNET, f"{s.failures} failures"))

    # Small models lose the thread on very long contexts even for easy asks.
    if s.context_tokens > p.haiku_context_ceiling_tokens:
        out.append(Contribution("context_ceiling", "floor", SONNET,
                                f"~{s.context_tokens} tok > {p.haiku_context_ceiling_tokens}"))
    return out


def evaluate(s: Signals, cfg: Config) -> Verdict:
    """Score the request, apply floors and ceilings, and explain every step."""
    p = cfg.policy

    if s.override_tier:
        pin = tier_index(s.override_tier)
        return Verdict(
            tier=pin, score=0.0, source="override",
            contributions=[Contribution("user_override", "pin", pin, f"!{s.override_tier} in prompt")],
        )

    contributions = _score_rules(s, cfg)
    score = sum(float(c.value) for c in contributions if c.kind == "score")
    score = max(-1.5, min(1.5, score))

    if score <= p.cheap_threshold:
        tier = HAIKU
    elif score >= p.expensive_threshold:
        tier = OPUS
    else:
        tier = tier_index(p.default_tier)

    floors = _floor_rules(s, cfg)
    contributions += floors
    applied_floor = max(int(c.value) for c in floors)
    if applied_floor > tier:
        tier = applied_floor

    ceiling = tier_index(p.max_tier)
    if tier > ceiling:
        contributions.append(Contribution("config_max_tier", "ceiling", ceiling, "configured ceiling"))
        tier = ceiling

    # A verdict sitting near a threshold is where a classifier earns its keep.
    band = cfg.llm.dead_band
    confident = not (p.cheap_threshold - band < score < p.cheap_threshold + band
                     or p.expensive_threshold - band < score < p.expensive_threshold + band)

    return Verdict(tier=tier, score=score, contributions=contributions, confident=confident)
