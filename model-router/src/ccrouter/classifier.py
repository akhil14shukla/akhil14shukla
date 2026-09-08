"""Optional local-LLM tiebreaker for requests the rules cannot call.

This only runs when the rule score lands in the dead band around a threshold,
so a slow or absent local model costs nothing on the requests that were already
clear-cut. Any failure -- timeout, connection refused, unparseable answer --
falls back to the rule verdict; the router never blocks on it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from collections import OrderedDict
from pathlib import Path

from .config import Config, tier_index, tier_name
from .rules import Contribution, Verdict
from .signals import Signals

_DEFAULT_TEMPLATE = """Pick the cheapest model that can do this correctly:
haiku (mechanical), sonnet (ordinary feature work), opus (design, debugging,
anything ambiguous). Rule engine said {{RULE_TIER}}.

{{PROMPT}}

Answer with one word: haiku, sonnet, or opus."""

_ANSWER = re.compile(r"\b(haiku|sonnet|opus)\b", re.I)


class _Cache(OrderedDict[str, str]):
    def __init__(self, limit: int) -> None:
        super().__init__()
        self.limit = limit

    def put(self, key: str, value: str) -> None:
        self[key] = value
        while len(self) > self.limit:
            self.popitem(last=False)


_cache: _Cache | None = None


def _cache_for(cfg: Config) -> _Cache:
    global _cache
    if _cache is None or _cache.limit != cfg.llm.cache_size:
        _cache = _Cache(cfg.llm.cache_size)
    return _cache


def load_template(cfg: Config) -> str:
    if cfg.llm.prompt_file:
        path = Path(cfg.llm.prompt_file).expanduser()
        if path.is_file():
            return path.read_text(encoding="utf-8")
    bundled = Path(__file__).resolve().parents[2] / "prompts" / "classify.md"
    if bundled.is_file():
        return bundled.read_text(encoding="utf-8")
    return _DEFAULT_TEMPLATE


def render(template: str, s: Signals, verdict: Verdict) -> str:
    facts = (
        f"phase={s.phase}, files={s.files_mentioned}, steps={s.enumerated_steps}, "
        f"failures={s.failures}, broad_scope={s.broad_scope}, "
        f"context~{s.context_tokens}tok, thinking={s.thinking_budget}"
    )
    return (
        template.replace("{{PROMPT}}", s.prompt[:4000])
        .replace("{{RULE_TIER}}", tier_name(verdict.tier))
        .replace("{{RULE_SCORE}}", f"{verdict.score:+.2f}")
        .replace("{{SIGNALS}}", facts)
    )


def _ask(cfg: Config, prompt: str) -> str:
    payload = json.dumps({
        "model": cfg.llm.model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 8,
        "stream": False,
    }).encode()
    headers = {"content-type": "application/json"}
    if cfg.llm.api_key_env and os.environ.get(cfg.llm.api_key_env):
        headers["authorization"] = f"Bearer {os.environ[cfg.llm.api_key_env]}"

    request = urllib.request.Request(cfg.llm.endpoint, data=payload, headers=headers)
    # A local endpoint must not be reached through a corporate proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=cfg.llm.timeout_s) as response:
        data = json.loads(response.read())
    return str(data["choices"][0]["message"]["content"])


def refine(verdict: Verdict, s: Signals, cfg: Config) -> Verdict:
    """Consult the local model only when the rules were genuinely undecided."""
    if not cfg.llm.enabled or verdict.confident or verdict.source == "override":
        return verdict
    if s.phase != "user_turn" or not s.prompt:
        return verdict

    prompt = render(load_template(cfg), s, verdict)
    key = hashlib.sha256(prompt.encode("utf-8", "replace")).hexdigest()
    cache = _cache_for(cfg)

    answer = cache.get(key)
    if answer is None:
        try:
            answer = _ask(cfg, prompt)
        except (urllib.error.URLError, OSError, KeyError, ValueError, TimeoutError) as exc:
            verdict.contributions.append(
                Contribution("llm_classifier", "score", 0.0, f"unavailable ({type(exc).__name__}), kept rule verdict")
            )
            return verdict
        cache.put(key, answer)

    match = _ANSWER.search(answer)
    if not match:
        verdict.contributions.append(
            Contribution("llm_classifier", "score", 0.0, f"unparseable answer {answer[:40]!r}")
        )
        return verdict

    chosen = tier_index(match.group(1))
    floor = max((int(c.value) for c in verdict.contributions if c.kind == "floor"), default=0)
    ceiling = min((int(c.value) for c in verdict.contributions if c.kind == "ceiling"), default=len(cfg.tiers) - 1)
    final = max(floor, min(ceiling, chosen))

    verdict.contributions.append(
        Contribution("llm_classifier", "pin", final,
                     f"{cfg.llm.model} said {match.group(1).lower()}"
                     + ("" if final == chosen else f", clamped to {tier_name(final)}"))
    )
    verdict.tier = final
    verdict.source = "llm"
    return verdict
