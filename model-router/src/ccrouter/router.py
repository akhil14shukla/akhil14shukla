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
import threading
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from . import classifier, rules, signals
from .config import HAIKU, Config, tier_name
from .rules import Contribution, Verdict


@dataclass
class _TurnState:
    turn_index: int
    tier: int
    escalated: bool
    updated: float


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

    def summary(self) -> str:
        arrow = f"{self.original_model} -> {self.model}" if self.rewrote else f"{self.model} (unchanged)"
        return f"[{tier_name(self.tier)}] {arrow}  via {self.source}"


class Router:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self._lock = threading.Lock()
        self._turns: OrderedDict[str, _TurnState] = OrderedDict()
        self._log_path = Path(os.path.expanduser(cfg.log_file))
        self.stats: dict[str, dict[str, float]] = {}

    # -- stickiness ------------------------------------------------------
    def _sticky(self, s: signals.Signals, verdict: Verdict) -> Verdict:
        if not self.cfg.policy.sticky_turns:
            return verdict
        with self._lock:
            state = self._turns.get(s.session_key)
            new_turn = state is None or s.turn_index > state.turn_index

            if new_turn or s.phase == "user_turn":
                self._turns[s.session_key] = _TurnState(
                    s.turn_index, verdict.tier, escalated=False, updated=time.time()
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

        verdict = rules.evaluate(s, cfg)
        verdict = classifier.refine(verdict, s, cfg)
        verdict = self._sticky(s, verdict)

        model = cfg.model_for(verdict.tier)
        return self._record(
            Decision(verdict.tier, model, original, verdict.source, verdict.score,
                     verdict.reasons, s.session_key, s.turn_index, s.phase,
                     s.context_tokens, model != original),
            s,
        )

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

    def savings(self) -> dict[str, Any]:
        """What the routed traffic cost, against everything-on-the-ceiling."""
        price = self.cfg.pricing_per_mtok_in
        ceiling = self.cfg.policy.max_tier
        routed = sum(
            b["input_tokens"] / 1e6 * price.get(tier, 0.0) for tier, b in self.stats.items()
        )
        baseline = sum(
            b["input_tokens"] / 1e6 * price.get(ceiling, 0.0) for b in self.stats.values()
        )
        return {
            "by_tier": self.stats,
            "estimated_input_cost_usd": round(routed, 4),
            "baseline_all_%s_usd" % ceiling: round(baseline, 4),
            "estimated_saving_usd": round(baseline - routed, 4),
            "note": "input tokens only, estimated at 4 chars/token from request bodies",
        }
