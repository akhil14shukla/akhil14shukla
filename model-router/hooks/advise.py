#!/usr/bin/env python3
"""UserPromptSubmit hook: advisory routing for when you are not running the proxy.

No hook can change the model for a request -- there is no `model` field in any
hook's output schema. What this hook *can* do is run the same rule engine on
the incoming prompt and tell Claude, in context, that the work it is about to
do is cheap enough to hand to a Haiku subagent (whose model frontmatter *is*
honoured), or expensive enough to be worth stopping to think about.

For actual enforcement, run `ccrouter serve` and set ANTHROPIC_BASE_URL.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ccrouter import config, rules, signals  # noqa: E402
from ccrouter.config import HAIKU, OPUS, tier_name  # noqa: E402

ADVICE = {
    HAIKU: (
        "Routing hint: this request scored as mechanical work ({score:+.2f}; {why}). "
        "If it needs more than a couple of tool calls, delegate it to the "
        "`model-router:quick` subagent, which runs on Haiku, instead of doing it "
        "on the current model."
    ),
    OPUS: (
        "Routing hint: this request scored as high-stakes work ({score:+.2f}; {why}). "
        "Prefer a plan before editing, and do not delegate it to a cheaper subagent."
    ),
}


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0

    prompt = event.get("user_input") or event.get("prompt") or ""
    if not prompt.strip():
        return 0

    cfg = config.load()
    body = {
        "model": cfg.policy.default_tier,
        "system": "You are Claude Code, Anthropic's official CLI for Claude.",
        "tools": [{"name": n} for n in ("Task", "Bash", "Read", "Edit", "Write")],
        "messages": [{"role": "user", "content": prompt}],
    }
    verdict = rules.evaluate(signals.extract(body, cfg), cfg)

    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "systemMessage": f"ccrouter: {tier_name(verdict.tier)} (score {verdict.score:+.2f})",
        }
    }
    template = ADVICE.get(verdict.tier)
    if template:
        why = "; ".join(
            c.detail for c in verdict.contributions if c.kind == "score" and c.detail
        )[:200]
        output["hookSpecificOutput"]["additionalContext"] = template.format(
            score=verdict.score, why=why or "no strong signals"
        )

    json.dump(output, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
