"""Turn ccrouter's decision log into labelled examples, using what happened next.

The label you want is not "what would a person call this request" -- it is
"what was the cheapest tier that actually finished this turn cleanly". The
decision log already knows, because every turn records whether the router had
to escalate.

    escalated mid-turn      -> the tier we started on was too low.
                               Label = the tier it ended on. Strong signal.
    finished, no escalation -> the tier we used was *sufficient*. Whether a
                               cheaper one would also have worked is unknown.
                               Weaker signal, and biased -- see below.

**The bias.** You only ever observe the outcome for the tier you actually
picked, so rows mined from normal traffic confirm the policy that produced
them. `router.py` fixes this by routing a small fraction of turns to a
neighbouring tier at random and marking them `source: "explore"`; those rows
are unbiased and are mined at full weight. Without exploration turned on, this
script still works, but it mostly teaches the model what the rules already
believe.

    python3 ml/mine.py --log ~/.claude/model-router/decisions.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from schema import TIERS, Example, describe, write

# How much to trust each kind of outcome.
WEIGHT_EXPLORED = 1.0        # randomised assignment: unbiased
WEIGHT_ESCALATED = 0.9       # we know the starting tier was too low
WEIGHT_CLEAN = 0.5           # sufficient, but possibly more than needed
WEIGHT_LONG = 0.3            # many steps, no escalation: ambiguous


def _turns(entries: list[dict[str, Any]]) -> dict[tuple[str, int], list[dict[str, Any]]]:
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        key = (str(entry.get("session_key", "")), int(entry.get("turn_index", 0)))
        grouped[key].append(entry)
    for steps in grouped.values():
        steps.sort(key=lambda e: e.get("ts", 0))
    return grouped


def _label_turn(steps: list[dict[str, Any]]) -> tuple[str, float, str] | None:
    """Return (label, weight, rationale) for one human turn, or None to skip."""
    tiers = [int(s.get("tier", 1)) for s in steps]
    sources = {str(s.get("source", "")) for s in steps}
    if not tiers:
        return None
    if "passthrough" in sources and len(sources) == 1:
        return None                                   # background call, not a turn

    started, ended = tiers[0], max(tiers)

    if "escalation" in sources:
        return (TIERS[ended], WEIGHT_ESCALATED,
                f"escalated {TIERS[started]} -> {TIERS[ended]} mid-turn")

    if "explore" in sources:
        return (TIERS[ended], WEIGHT_EXPLORED,
                f"randomised to {TIERS[ended]}, completed without escalation")

    if len(steps) > 12:
        return (TIERS[ended], WEIGHT_LONG,
                f"{len(steps)} steps on {TIERS[ended]} without escalation: ambiguous")

    return (TIERS[ended], WEIGHT_CLEAN,
            f"completed on {TIERS[ended]} in {len(steps)} steps, no escalation")


def mine(entries: list[dict[str, Any]], min_prompt_chars: int = 8) -> list[Example]:
    rows: list[Example] = []
    for (session_key, turn_index), steps in _turns(entries).items():
        prompt = next((str(s.get("prompt", "")) for s in steps if s.get("prompt")), "")
        if len(prompt.strip()) < min_prompt_chars:
            continue
        verdict = _label_turn(steps)
        if verdict is None:
            continue
        label, weight, rationale = verdict

        first = steps[0]
        signals = dict(first.get("signals") or {})
        signals.setdefault("phase", first.get("phase", "user_turn"))
        signals.setdefault("context_tokens", first.get("context_tokens", 0))
        # What the loop went on to look like is part of the evidence.
        signals["failures"] = max(int(s.get("signals", {}).get("failures", 0)) for s in steps)

        rows.append(Example(
            prompt=prompt,
            label=label,
            source="mined",
            label_source="outcome",
            weight=weight,
            group=f"{session_key}:{turn_index}",
            signals=signals,
            rationale=rationale,
        ))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", default="~/.claude/model-router/decisions.jsonl")
    parser.add_argument("--out", default="ml/dataset/mined.jsonl")
    args = parser.parse_args(argv)

    path = Path(os.path.expanduser(args.log))
    if not path.is_file():
        print(f"no decision log at {path} -- run the proxy first", file=sys.stderr)
        return 1

    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                entries.append(json.loads(line))
            except ValueError:
                continue

    rows = mine(entries)
    if not rows:
        print("no complete turns found in the log", file=sys.stderr)
        return 1

    write(args.out, rows)
    explored = sum(1 for r in rows if r.weight == WEIGHT_EXPLORED)
    print(f"wrote {args.out}")
    print(describe(rows))
    print(f"\n  {explored}/{len(rows)} rows come from randomised exploration.")
    if explored < len(rows) * 0.05:
        print("  !! Little or no exploration in this log. These labels mostly confirm\n"
              "     the policy that produced them. Set policy.explore_rate in router.toml.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
