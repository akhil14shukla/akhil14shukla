"""Expand the taxonomy into a seed dataset.

Deterministic: same seed, same rows. Seed rows are train-only (schema.TRAIN_ONLY)
because grading a model on the taxonomy that generated it tells you nothing.

    python3 ml/seed.py --out ml/dataset/seed.jsonl --per-template 6
"""

from __future__ import annotations

import argparse
import itertools
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import taxonomy as tax
from schema import Example, describe, write

_SLOT = re.compile(r"\{(\w+)\}")


def _fill(template: str, rng: random.Random) -> str:
    """Fill slots, sampling once per slot name so one prompt stays coherent."""
    chosen: dict[str, str] = {}

    def pick(match: re.Match[str]) -> str:
        name = match.group(1)
        options = tax.SLOTS.get(name)
        if not options:
            return match.group(0)
        return chosen.setdefault(name, rng.choice(options))

    return _SLOT.sub(pick, template)


def _decorate(text: str, rng: random.Random) -> str:
    body = rng.choice(tax.PREFIXES) + text + rng.choice(tax.SUFFIXES)
    return body[0].upper() + body[1:] if rng.random() < 0.3 else body


def _archetype_rows(per_template: int, rng: random.Random) -> list[Example]:
    rows: list[Example] = []
    for archetype in tax.ARCHETYPES:
        for index, template in enumerate(archetype.templates):
            seen: set[str] = set()
            for _ in range(per_template * 3):          # oversample, then dedupe
                prompt = _decorate(_fill(template, rng), rng)
                if prompt.lower() in seen:
                    continue
                seen.add(prompt.lower())
                rows.append(Example(
                    prompt=prompt,
                    label=archetype.tier,
                    source="seed",
                    label_source="taxonomy",
                    weight=0.7,          # synthetic: real labels should outvote it
                    group=f"arch:{archetype.name}:{index}",
                    rationale=archetype.why,
                    signals={"phase": "user_turn"},
                ))
                if len(seen) >= per_template:
                    break
    return rows


def _contrast_rows(per_pair: int, rng: random.Random) -> list[Example]:
    """Minimal pairs. Both sides share a group so they never straddle a split."""
    rows: list[Example] = []
    for index, (cheap, cheap_tier, harder, hard_tier, shared) in enumerate(tax.CONTRASTS):
        group = f"contrast:{index}"
        for _ in range(per_pair):
            fills = {slot: rng.choice(values) for slot, values in tax.SLOTS.items()}
            for template, tier in ((cheap, cheap_tier), (harder, hard_tier)):
                prompt = _SLOT.sub(lambda m: fills.get(m.group(1), m.group(0)), template)
                rows.append(Example(
                    prompt=_decorate(prompt, rng),
                    label=tier,
                    source="seed",
                    label_source="taxonomy",
                    weight=1.0,          # these carry the signal that matters most
                    group=group,
                    rationale=f"minimal pair on {shared!r}: surface overlap, different work",
                    signals={"phase": "user_turn"},
                ))
    return rows


def _followup_rows(per_item: int, rng: random.Random) -> list[Example]:
    """Mid-loop asks, where position in the conversation carries the meaning."""
    rows: list[Example] = []
    for index, (tier, prompt) in enumerate(tax.FOLLOWUPS):
        for _ in range(per_item):
            failures = rng.randint(2, 4) if tier == "opus" else 0
            rows.append(Example(
                prompt=prompt,
                label=tier,
                source="seed",
                label_source="taxonomy",
                weight=0.8,
                group=f"followup:{index}",
                rationale="continuation; loop state carries the meaning",
                signals={
                    "phase": "tool_loop",
                    "failures": failures,
                    "recent_tools_readonly": tier == "haiku",
                    "thrash": 2 if tier == "opus" and failures > 2 else 0,
                },
            ))
    return rows


def build(per_template: int = 6, per_pair: int = 4, seed: int = 20260908) -> list[Example]:
    rng = random.Random(seed)
    rows = list(itertools.chain(
        _archetype_rows(per_template, rng),
        _contrast_rows(per_pair, rng),
        _followup_rows(max(2, per_pair // 2), rng),
    ))
    rng.shuffle(rows)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="ml/dataset/seed.jsonl")
    parser.add_argument("--per-template", type=int, default=6)
    parser.add_argument("--per-pair", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20260908)
    args = parser.parse_args(argv)

    rows = build(args.per_template, args.per_pair, args.seed)
    write(args.out, rows)
    print(f"wrote {args.out}")
    print(describe(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
