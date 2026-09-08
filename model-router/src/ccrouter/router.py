"""Decision layer: rules + classifier + turn stickiness + the decision log.

Stickiness is the part that is easy to leave out and expensive to omit. A
single user turn produces many API calls -- one per step of the agentic loop --
and flipping models between them both loses the prompt cache and lets the
agent contradict itself mid-task. So the tier is chosen once when a new human
turn arrives, then pinned for the rest of that turn. Escalation is the one
thing allowed to break the pin: if the loop starts failing, we upgrade
immediately and never fall back down within the turn.
"""

from __future__ import annotations

import json
import os
import random
import threading
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import classifier, economics, rules, semantic, signals
from .config import HAIKU, Config, tier_index, tier_name
from .rules import Contribution, Verdict


@dataclass
class _TurnState:
    turn_index: int
    tier: int
    escalated: bool
    updated: float
    steps: int = 1
    warm_tier: int = -1        # the tier whose prompt cache is currently warm
    context_tokens: int = 0


@dataclass
class Decision:
    tier: int
    model: str
    original_model: str
    source: str
    score: float
    reasons: list[str]
    session_key: str
    turn_index: int
    phase: str
    context_tokens: int
    rewrote: bool
    signals: dict[str, Any] = field(default_factory=dict)
    rewarm_usd: float = 0.0        # cache rebuild this decision paid for
    step: int = 1

    def summary(self) -> str:
        arrow = f"{self.original_model} -> {self.model}" if self.rewrote else f"{self.model} (unchanged)"
        return f"[{tier_name(self.tier)}] {arrow}  via {self.source}"


class Router:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self._lock = threading.Lock()
        self._turns: OrderedDict[str, _TurnState] = OrderedDict()
        self._log_path = Path(os.path.expanduser(cfg.log_file))
        self._rng = random.Random()
        self._turn_length = economics.TurnLength(cfg.policy.expected_turn_length)
        self.rewarm_usd = 0.0                 # modelled, before responses arrive
        self.measured_rewarm_usd = 0.0        # billed, from cache_creation tokens
        self.measured: dict[str, dict[str, int]] = {}
        self.stats: dict[str, dict[str, float]] = {}

    # -- stickiness ------------------------------------------------------
    def _sticky(self, s: signals.Signals, verdict: Verdict) -> Verdict:
        if not self.cfg.policy.sticky_turns:
            return verdict
        with self._lock:
            state = self._turns.get(s.session_key)
            new_turn = state is None or s.turn_index > state.turn_index

            if new_turn or s.phase == "user_turn":
                if state is not None:
                    self._turn_length.observe(state.steps)
                self._turns[s.session_key] = _TurnState(
                    s.turn_index, verdict.tier, escalated=False, updated=time.time(),
                    warm_tier=state.warm_tier if state else -1,
                    context_tokens=s.context_tokens,
                )
                while len(self._turns) > 512:
                    self._turns.popitem(last=False)
                return verdict

            assert state is not None
            if verdict.tier > state.tier:
                # Escalation always wins: the loop is in trouble.
                verdict.contributions.append(
                    Contribution("escalated", "pin", verdict.tier,
                                 f"upgraded from {tier_name(state.tier)} mid-turn")
                )
                state.tier, state.escalated, state.updated = verdict.tier, True, time.time()
                verdict.source = "escalation"
                return verdict

            if verdict.tier < state.tier and not self.cfg.policy.allow_mid_turn_downgrade:
                verdict.contributions.append(
                    Contribution("sticky_turn", "pin", state.tier,
                                 f"pinned for turn {state.turn_index}"
                                 + (" after escalation" if state.escalated else ""))
                )
                verdict.tier = state.tier
                verdict.source = "sticky"
            return verdict

    def _explore(self, s: signals.Signals, verdict: Verdict) -> Verdict:
        """Occasionally route a fresh turn to a neighbouring tier, on purpose.

        Mined outcomes are otherwise only ever observed for the tier the policy
        already chose, so they confirm the policy rather than test it. A small
        randomised slice is what makes the training data unbiased -- and it is
        clamped inside the floors, so exploration never overrides a safety rule.
        """
        rate = self.cfg.policy.explore_rate
        if rate <= 0 or s.phase != "user_turn" or verdict.source not in ("rules", "llm"):
            return verdict
        if self._rng.random() >= rate:
            return verdict

        floor = max((int(c.value) for c in verdict.contributions if c.kind == "floor"), default=0)
        ceiling = min((int(c.value) for c in verdict.contributions if c.kind == "ceiling"),
                      default=tier_index(self.cfg.policy.max_tier))
        options = [t for t in (verdict.tier - 1, verdict.tier + 1) if floor <= t <= ceiling]
        if not options:
            return verdict

        chosen = self._rng.choice(options)
        verdict.contributions.append(Contribution(
            "exploration", "pin", chosen,
            f"randomised from {tier_name(verdict.tier)} for unbiased training data"))
        verdict.tier = chosen
        verdict.source = "explore"
        return verdict

    def _cache_gate(
        self, s: signals.Signals, verdict: Verdict, state: _TurnState | None
    ) -> tuple[Verdict, float]:
        """Refuse a *downgrade* that costs more to re-warm than it will save.

        Prompt caches are model-scoped, so changing models throws away the warm
        prefix and pays to rebuild it elsewhere. At a large context most
        downgrades never earn that back: sonnet -> haiku at 50k tokens saves
        under a cent per request and costs ten to re-warm, so it only pays if
        thirteen more requests follow. Typical turns are shorter than that.

        The gate deliberately only looks at downgrades. An upgrade is a quality
        decision -- the loop is failing, or the work turned out to be harder
        than it looked -- and no cache saving justifies staying on a model that
        cannot do the job. Upgrades pass through with their cost recorded, so
        `ccrouter stats` can show what escalation actually cost.

        User overrides and exploration are exempt in both directions: one is an
        instruction, and the other exists precisely to sample tiers the policy
        would not otherwise pick.
        """
        cfg = self.cfg
        warm = state.warm_tier if state and state.warm_tier >= 0 else -1
        if warm < 0 or warm == verdict.tier:
            return verdict, 0.0

        horizon = self._turn_length.expected_remaining(state.steps if state else 0)
        analysis = economics.analyse_switch(
            cfg, warm, verdict.tier, s.context_tokens, horizon)
        move = f"{tier_name(warm)}->{tier_name(verdict.tier)}"

        exempt = (
            verdict.tier > warm                              # upgrades are quality
            or verdict.source in ("override", "explore")
            or not cfg.policy.switch_must_pay_for_itself
        )
        if exempt:
            verdict.contributions.append(Contribution(
                "cache_rewarm", "score", 0.0,
                f"{move} re-warms the prompt cache for ${analysis.rewarm_cost:.4f}"))
            return verdict, analysis.rewarm_cost

        if analysis.net_saving > cfg.policy.min_switch_saving_usd:
            verdict.contributions.append(Contribution(
                "cache_rewarm", "score", 0.0,
                f"{move} pays: {analysis.detail}, net ${analysis.net_saving:+.4f}"))
            return verdict, analysis.rewarm_cost

        verdict.contributions.append(Contribution(
            "cache_hold", "pin", warm,
            f"held on {tier_name(warm)}: {move} saves "
            f"${analysis.saving_per_request:.4f}/req but costs "
            f"${analysis.rewarm_cost:.4f} to re-warm ({analysis.detail})"))
        verdict.tier = warm
        verdict.source = "cache_hold"
        return verdict, 0.0

    # -- main entry point -------------------------------------------------
    def decide(self, body: dict[str, Any]) -> Decision:
        cfg = self.cfg
        s = signals.extract(body, cfg)
        original = s.requested_model

        requested_tier = cfg.tier_of_model(original)
        if cfg.policy.passthrough_background and requested_tier == HAIKU and not s.tool_names:
            # Claude Code's own housekeeping calls (titles, summaries) already
            # ask for the small model. Leave them alone.
            return self._record(
                Decision(HAIKU, original, original, "passthrough", 0.0,
                         ["background_call     passthrough  no tools offered"],
                         s.session_key, s.turn_index, s.phase, s.context_tokens, False),
                s,
            )

        verdict = rules.evaluate(s, cfg, semantic=semantic.score_for(s.prompt, s, cfg))
        verdict = classifier.refine(verdict, s, cfg)
        verdict = self._explore(s, verdict)
        verdict = self._sticky(s, verdict)

        with self._lock:
            state = self._turns.get(s.session_key)
        verdict, rewarm = self._cache_gate(s, verdict, state)
        step = self._advance(s, verdict.tier, rewarm)

        model = cfg.model_for(verdict.tier)
        return self._record(
            Decision(verdict.tier, model, original, verdict.source, verdict.score,
                     verdict.reasons, s.session_key, s.turn_index, s.phase,
                     s.context_tokens, model != original, semantic.signals_dict(s),
                     rewarm, step),
            s,
        )

    def _advance(self, s: signals.Signals, tier: int, rewarm: float) -> int:
        """Record which tier is now warm, and how long turns are running."""
        with self._lock:
            state = self._turns.get(s.session_key)
            if state is None:
                return 1
            if state.warm_tier >= 0 and state.warm_tier != tier:
                self.rewarm_usd += rewarm
            state.warm_tier = tier
            state.context_tokens = s.context_tokens
            if s.phase == "tool_loop":
                state.steps += 1
            return state.steps

    # -- observability ----------------------------------------------------
    def _record(self, decision: Decision, s: signals.Signals) -> Decision:
        bucket = self.stats.setdefault(tier_name(decision.tier), {"calls": 0, "input_tokens": 0})
        bucket["calls"] += 1
        bucket["input_tokens"] += decision.context_tokens

        entry = {"ts": round(time.time(), 3), "prompt": s.prompt[:280], **asdict(decision)}
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, default=str) + "\n")
        except OSError:
            pass  # Logging must never take the proxy down.
        return decision

    def observe_usage(self, decision: "Decision | None", usage: dict[str, int]) -> None:
        """Record what the API actually billed, replacing the 4-chars/token guess.

        `cache_creation_input_tokens` on a request that changed models *is* the
        re-warm, measured rather than modelled -- so the cost of switching stops
        being an estimate as soon as real traffic flows through.
        """
        if decision is None or not usage:
            return
        name = tier_name(decision.tier)
        with self._lock:
            bucket = self.measured.setdefault(name, {
                "calls": 0, "input_tokens": 0, "output_tokens": 0,
                "cache_read": 0, "cache_write": 0,
            })
            bucket["calls"] += 1
            bucket["input_tokens"] += usage.get("input_tokens", 0)
            bucket["output_tokens"] += usage.get("output_tokens", 0)
            bucket["cache_read"] += usage.get("cache_read_input_tokens", 0)
            written = usage.get("cache_creation_input_tokens", 0)
            bucket["cache_write"] += written
            if decision.rewarm_usd and written:
                cache = economics.CacheModel.for_ttl(self.cfg.cache_ttl)
                price = self.cfg.pricing_per_mtok_in.get(name, 0.0) / 1e6
                self.measured_rewarm_usd += written * cache.write_multiplier * price

    def _measured_cost(self, tier_for_pricing: str | None = None) -> float:
        cache = economics.CacheModel.for_ttl(self.cfg.cache_ttl)
        total = 0.0
        for name, bucket in self.measured.items():
            priced = tier_for_pricing or name
            price_in = self.cfg.pricing_per_mtok_in.get(priced, 0.0) / 1e6
            price_out = self.cfg.pricing_per_mtok_out.get(priced, 0.0) / 1e6
            total += (
                bucket["input_tokens"] * price_in
                + bucket["cache_read"] * cache.read_multiplier * price_in
                + bucket["cache_write"] * cache.write_multiplier * price_in
                + bucket["output_tokens"] * price_out
            )
        return total

    def savings(self) -> dict[str, Any]:
        """What the routed traffic cost, against everything on the ceiling tier.

        Reports measured numbers once responses have flowed through the proxy,
        and falls back to a token estimate before that. Both are net of what
        re-warming the prompt cache cost, which an earlier version of this
        report ignored and therefore overstated.
        """
        ceiling = self.cfg.policy.max_tier
        report: dict[str, Any] = {"by_tier": self.stats}

        if self.measured:
            routed = self._measured_cost()
            baseline = self._measured_cost(ceiling)
            report.update({
                "basis": "measured from response usage",
                "measured_by_tier": self.measured,
                "cost_usd": round(routed, 4),
                f"baseline_all_{ceiling}_usd": round(baseline, 4),
                "cache_rewarm_usd": round(self.measured_rewarm_usd, 4),
                "net_saving_usd": round(baseline - routed, 4),
            })
            return report

        price = self.cfg.pricing_per_mtok_in
        routed = sum(b["input_tokens"] / 1e6 * price.get(tier, 0.0)
                     for tier, b in self.stats.items())
        baseline = sum(b["input_tokens"] / 1e6 * price.get(ceiling, 0.0)
                       for b in self.stats.values())
        report.update({
            "basis": "estimated at 4 chars/token; no responses observed yet",
            "cost_usd": round(routed, 4),
            f"baseline_all_{ceiling}_usd": round(baseline, 4),
            "cache_rewarm_usd": round(self.rewarm_usd, 4),
            "net_saving_usd": round(baseline - routed - self.rewarm_usd, 4),
            "expected_turn_length": round(
                self._turn_length.expected_remaining(0), 1),
            "turn_samples": self._turn_length.samples,
        })
        return report
