"""Label prompts with Claude Opus 5 via the Batch API, to distil into the small model.

Batch runs at 50% of standard prices and is exactly the right shape for this:
thousands of independent one-word classifications with no latency requirement.

`--dry-run` is the default. It prints the token and dollar estimate and writes
nothing, because every real run spends money.

    python3 ml/label.py --prompts prompts.txt                  # estimate only
    python3 ml/label.py --prompts prompts.txt --submit         # actually spend
    python3 ml/label.py --collect batch_01xyz --out ml/dataset/distilled.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from schema import TIERS, Example, describe, write

MODEL = "claude-opus-5"
# USD per million tokens for MODEL, before the Batch API's 50% discount.
PRICE_IN, PRICE_OUT = 5.00, 25.00
BATCH_DISCOUNT = 0.5

INSTRUCTION = """You are labelling training data for a model router that sits in \
front of a coding agent. For each request, pick the cheapest model tier that \
could complete it correctly on the first attempt.

haiku  - mechanical and fully specified, low blast radius: reading or summarising
         files, single-file edits, renames, formatting, running a command and
         reporting output, answering a factual question about code in context.
sonnet - ordinary feature work: writing a function or a test, wiring existing
         pieces together, a contained change where the approach is already clear.
opus   - work where a wrong approach is expensive: architecture and design,
         debugging something intermittent or not yet understood, concurrency,
         security, performance analysis, migrations, or a request that is
         ambiguous about what "correct" would even mean.

Judge the work the request implies, not how politely or briefly it is phrased.
A three-word request that names nothing ("clean this up") needs judgement and is
not cheap. When genuinely torn between two tiers, pick the more capable one: a
retry costs more than the upgrade would have.

Set confidence below 0.6 when the request could reasonably sit in either of two
tiers -- those rows are the ones worth a human look."""

SCHEMA = {
    "type": "object",
    "properties": {
        "tier": {"type": "string", "enum": list(TIERS)},
        "confidence": {"type": "number"},
        "rationale": {"type": "string"},
    },
    "required": ["tier", "confidence", "rationale"],
    "additionalProperties": False,
}


def _read_prompts(path: str) -> list[str]:
    text = Path(path).read_text(encoding="utf-8")
    if path.endswith(".jsonl"):
        out = []
        for line in text.splitlines():
            if line.strip():
                row = json.loads(line)
                out.append(str(row.get("prompt", "")))
        return [p for p in out if p.strip()]
    return [line.strip() for line in text.splitlines() if line.strip()]


def estimate(prompts: list[str], max_tokens: int) -> dict[str, float]:
    instruction_tokens = len(INSTRUCTION) // 4
    input_tokens = sum(instruction_tokens + len(p) // 4 + 20 for p in prompts)
    # Adaptive thinking at low effort; most of the budget goes unused.
    output_tokens = len(prompts) * min(max_tokens, 250)
    standard = input_tokens / 1e6 * PRICE_IN + output_tokens / 1e6 * PRICE_OUT
    return {
        "requests": len(prompts),
        "input_tokens": input_tokens,
        "output_tokens_assumed": output_tokens,
        "standard_usd": round(standard, 2),
        "batch_usd": round(standard * BATCH_DISCOUNT, 2),
    }


def submit(prompts: list[str], max_tokens: int) -> str:
    import anthropic
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    client = anthropic.Anthropic()
    batch = client.messages.batches.create(requests=[
        Request(
            custom_id=f"p{index}",
            params=MessageCreateParamsNonStreaming(
                model=MODEL,
                max_tokens=max_tokens,
                system=INSTRUCTION,
                output_config={"format": {"type": "json_schema", "schema": SCHEMA},
                               "effort": "low"},
                messages=[{"role": "user", "content": prompt}],
            ),
        )
        for index, prompt in enumerate(prompts)
    ])
    return batch.id


def collect(batch_id: str, prompts: list[str], wait: bool) -> list[Example]:
    import anthropic

    client = anthropic.Anthropic()
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        if batch.processing_status == "ended" or not wait:
            break
        counts = batch.request_counts
        print(f"  {batch.processing_status}: {counts.succeeded} done, "
              f"{counts.processing} processing, {counts.errored} errored")
        time.sleep(30)

    if batch.processing_status != "ended":
        print(f"batch is {batch.processing_status}, not ended", file=sys.stderr)
        return []

    rows: list[Example] = []
    errors = 0
    for result in client.messages.batches.results(batch_id):
        if result.result.type != "succeeded":
            errors += 1
            continue
        index = int(result.custom_id.lstrip("p"))
        message = result.result.message
        text = next((b.text for b in message.content if b.type == "text"), "")
        try:
            parsed = json.loads(text)
        except ValueError:
            errors += 1
            continue
        rows.append(Example(
            prompt=prompts[index],
            label=parsed["tier"],
            source="distilled",
            label_source=MODEL,
            weight=float(parsed.get("confidence", 0.8)),
            rationale=str(parsed.get("rationale", ""))[:300],
            signals={"phase": "user_turn"},
        ))
    if errors:
        print(f"  {errors} request(s) did not yield a label", file=sys.stderr)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompts", help="one prompt per line, or a .jsonl with a prompt field")
    parser.add_argument("--out", default="ml/dataset/distilled.jsonl")
    parser.add_argument("--max-tokens", type=int, default=2000)
    parser.add_argument("--submit", action="store_true", help="actually create the batch")
    parser.add_argument("--collect", help="batch id to collect results from")
    parser.add_argument("--no-wait", action="store_true")
    args = parser.parse_args(argv)

    if not args.prompts:
        parser.error("--prompts is required (it is also needed to collect: it maps ids back)")
    prompts = _read_prompts(args.prompts)
    if not prompts:
        print(f"no prompts in {args.prompts}", file=sys.stderr)
        return 1

    if args.collect:
        rows = collect(args.collect, prompts, wait=not args.no_wait)
        if not rows:
            return 1
        write(args.out, rows)
        print(f"wrote {args.out}")
        print(describe(rows))
        low = [r for r in rows if r.weight < 0.6]
        print(f"\n  {len(low)} row(s) below 0.6 confidence -- review these by hand;"
              "\n  they sit on a tier boundary and are worth more than the confident ones.")
        return 0

    costs = estimate(prompts, args.max_tokens)
    print(f"{costs['requests']} prompts, model {MODEL}")
    print(f"  ~{costs['input_tokens']:,} input tokens, "
          f"~{costs['output_tokens_assumed']:,} output tokens assumed")
    print(f"  standard: ${costs['standard_usd']}   batch (50% off): ${costs['batch_usd']}")

    if not args.submit:
        print("\ndry run -- nothing submitted. Re-run with --submit to spend this.")
        return 0

    batch_id = submit(prompts, args.max_tokens)
    print(f"\nsubmitted batch {batch_id}")
    print(f"collect with:\n  python3 ml/label.py --prompts {args.prompts} "
          f"--collect {batch_id} --out {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
