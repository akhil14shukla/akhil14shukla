"""Optional semantic scorer: what the prompt *means*, not which words it uses.

The rule lexicon matches phrases. That fails in both directions -- "rename X in
one file" and "rename X everywhere and keep the API compatible" share a verb and
almost nothing else, and no realistic word list separates them. A small learned
model over sentence embeddings does.

The model here is a linear classifier over a static embedding, exported by
`ml/train.py` as plain numpy arrays. Static embeddings are a token-vector lookup
plus a mean, so scoring costs tens of microseconds on a CPU with no torch
loaded -- which is what makes this affordable in front of every API call.

Everything is optional and fails open. If numpy, model2vec, or the exported
model is missing, the scorer reports itself unavailable and the router falls
back to rules exactly as before.
"""

from __future__ import annotations

import math
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Canonical feature order, shared with training (ml/features.py imports it).
STRUCTURAL_KEYS: tuple[str, ...] = (
    "is_user_turn", "is_tool_loop", "is_subagent",
    "failures", "thrash", "files_mentioned", "enumerated_steps",
    "broad_scope", "has_stacktrace", "is_question", "underspecified",
    "recent_tools_readonly", "log_thinking_budget", "log_context_tokens",
    "log_prompt_chars", "log_n_messages",
)


def _log1p(value: Any) -> float:
    try:
        return math.log1p(max(0.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def structural_vector(signals: dict[str, Any], prompt: str = "") -> list[float]:
    """Map a signals dict (possibly partial) onto STRUCTURAL_KEYS order."""
    phase = str(signals.get("phase", "user_turn"))
    return [
        float(phase == "user_turn"),
        float(phase == "tool_loop"),
        float(bool(signals.get("is_subagent"))),
        float(signals.get("failures", 0) or 0),
        float(signals.get("thrash", 0) or 0),
        float(signals.get("files_mentioned", 0) or 0),
        float(signals.get("enumerated_steps", 0) or 0),
        float(bool(signals.get("broad_scope"))),
        float(bool(signals.get("has_stacktrace"))),
        float(bool(signals.get("is_question"))),
        float(bool(signals.get("underspecified"))),
        float(bool(signals.get("recent_tools_readonly"))),
        _log1p(signals.get("thinking_budget", 0)),
        _log1p(signals.get("context_tokens", 0)),
        _log1p(signals.get("prompt_chars", len(prompt))),
        _log1p(signals.get("n_messages", 0)),
    ]


def signals_dict(s: Any) -> dict[str, Any]:
    """Project a ccrouter Signals object onto the dict the feature order expects."""
    return {
        "phase": getattr(s, "phase", "user_turn"),
        "is_subagent": getattr(s, "is_subagent", False),
        "failures": getattr(s, "failures", 0),
        "thrash": getattr(s, "thrash", 0),
        "files_mentioned": getattr(s, "files_mentioned", 0),
        "enumerated_steps": getattr(s, "enumerated_steps", 0),
        "broad_scope": getattr(s, "broad_scope", False),
        "has_stacktrace": getattr(s, "has_stacktrace", False),
        "is_question": getattr(s, "is_question", False),
        "underspecified": getattr(s, "underspecified", False),
        "recent_tools_readonly": getattr(s, "recent_tools_readonly", False),
        "thinking_budget": getattr(s, "thinking_budget", 0),
        "context_tokens": getattr(s, "context_tokens", 0),
        "prompt_chars": getattr(s, "prompt_chars", 0),
        "n_messages": getattr(s, "n_messages", 0),
    }


@dataclass
class Prediction:
    probabilities: dict[str, float]
    tier: str
    margin: float          # P(opus) - P(haiku), in [-1, 1]

    @property
    def confidence(self) -> float:
        return max(self.probabilities.values(), default=0.0)


class Scorer:
    """Lazily loads the exported model; unavailable is a normal, silent state."""

    def __init__(self, model_path: str, encoder: str = "") -> None:
        self.model_path = os.path.expanduser(model_path)
        self.encoder_override = encoder
        self.error: str = ""
        self._lock = threading.Lock()
        self._ready: bool | None = None
        self._np: Any = None
        self._model: Any = None
        self._weights: dict[str, Any] = {}

    @property
    def available(self) -> bool:
        if self._ready is None:
            with self._lock:
                if self._ready is None:
                    self._ready = self._load()
        return bool(self._ready)

    def _load(self) -> bool:
        if not Path(self.model_path).is_file():
            self.error = f"no model at {self.model_path}"
            return False
        try:
            import numpy as np
            from model2vec import StaticModel
        except ImportError as exc:
            self.error = f"{exc.name} not installed (pip install numpy model2vec)"
            return False
        try:
            data = np.load(self.model_path, allow_pickle=False)
            self._weights = {
                "coef": data["coef"], "intercept": data["intercept"],
                "mean": data["mean"], "scale": data["scale"],
                "classes": [str(c) for c in data["classes"]],
                "blocks": str(data["blocks"]),
            }
            encoder = self.encoder_override or str(data["encoder"])
            self._model = StaticModel.from_pretrained(encoder)
            self._np = np
        except (OSError, KeyError, ValueError) as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            return False
        return True

    def _features(self, prompt: str, signals: dict[str, Any]) -> Any:
        np = self._np
        blocks = self._weights["blocks"]
        parts: list[Any] = []
        if blocks in ("semantic", "both"):
            parts.append(np.asarray(self._model.encode([prompt])[0], dtype=np.float32))
        if blocks in ("structural", "both"):
            parts.append(np.asarray(structural_vector(signals, prompt), dtype=np.float32))
        return np.concatenate(parts)

    def predict(self, prompt: str, signals: dict[str, Any] | None = None) -> Prediction | None:
        if not self.available or not prompt.strip():
            return None
        np = self._np
        w = self._weights
        try:
            x = (self._features(prompt, signals or {}) - w["mean"]) / w["scale"]
            logits = w["coef"] @ x + w["intercept"]
            logits = logits - logits.max()
            exp = np.exp(logits)
            probabilities = dict(zip(w["classes"], (exp / exp.sum()).tolist()))
        except (ValueError, FloatingPointError) as exc:
            self.error = f"scoring failed: {type(exc).__name__}: {exc}"
            return None

        best = max(probabilities, key=probabilities.get)
        margin = probabilities.get("opus", 0.0) - probabilities.get("haiku", 0.0)
        return Prediction(probabilities=probabilities, tier=best, margin=margin)


_scorers: dict[tuple[str, str], Scorer] = {}
_scorers_lock = threading.Lock()


def get(model_path: str, encoder: str = "") -> Scorer:
    """One scorer per (path, encoder) -- the embedding table is worth reusing."""
    key = (os.path.expanduser(model_path), encoder)
    with _scorers_lock:
        if key not in _scorers:
            _scorers[key] = Scorer(*key)
        return _scorers[key]


def score_for(prompt: str, signals: Any, cfg: Any) -> tuple[float, str] | None:
    """Return (score_delta, detail) to fold into the rule engine, or None.

    The delta is the model's opus-vs-haiku margin scaled by a configured weight,
    so it composes with the existing additive score and can never bypass a floor.
    """
    semantic = getattr(cfg, "semantic", None)
    if semantic is None or not getattr(semantic, "enabled", False):
        return None
    scorer = get(semantic.model_path, semantic.encoder)
    prediction = scorer.predict(prompt, signals_dict(signals))
    if prediction is None:
        return None
    if prediction.confidence < semantic.min_confidence:
        return None
    return (
        semantic.weight * prediction.margin,
        f"{prediction.tier} p={prediction.confidence:.2f} margin={prediction.margin:+.2f}",
    )
