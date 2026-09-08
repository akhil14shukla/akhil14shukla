"""The dataset contract: one Example per row, and how rows become splits.

Stdlib only, so the schema and the split policy can be tested without any of
the training dependencies installed.

Split policy is enforced here rather than left to a flag, because the two ways
this dataset can lie to you are both split bugs:

* synthetic seed rows in the test set flatter the score -- the model is being
  graded on the taxonomy that generated it, not on real traffic;
* paraphrases of one prompt landing on both sides leak the answer.

So seed rows are train-only by construction, hand-labelled golden rows are
test-only, and everything else is hashed by `group` so all variants of a
prompt move together.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Literal

Tier = Literal["haiku", "sonnet", "opus"]
TIERS: tuple[str, ...] = ("haiku", "sonnet", "opus")

# Where a row came from. Drives the split policy below.
Source = Literal["seed", "mined", "distilled", "golden"]

TRAIN_ONLY: frozenset[str] = frozenset({"seed"})
TEST_ONLY: frozenset[str] = frozenset({"golden"})


@dataclass
class Example:
    prompt: str
    label: str
    source: str
    label_source: str = ""          # taxonomy | outcome | claude-opus-5 | human
    weight: float = 1.0             # confidence; mined rows carry < 1.0
    group: str = ""                 # variants of one prompt share this
    signals: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    id: str = ""
    created: float = field(default_factory=lambda: round(time.time(), 3))

    def __post_init__(self) -> None:
        if self.label not in TIERS:
            raise ValueError(f"label {self.label!r} not in {TIERS}")
        if not self.prompt.strip():
            raise ValueError("prompt is empty")
        if not self.group:
            self.group = hashlib.sha1(self.prompt.lower().encode()).hexdigest()[:12]
        if not self.id:
            payload = f"{self.source}\x00{self.prompt}\x00{self.label}"
            self.id = hashlib.sha1(payload.encode()).hexdigest()[:16]


def write(path: str | Path, examples: Iterable[Example]) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for example in examples:
            handle.write(json.dumps(asdict(example), ensure_ascii=False) + "\n")
            count += 1
    return count


def read(*paths: str | Path) -> list[Example]:
    out: list[Example] = []
    for path in paths:
        p = Path(path)
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(Example(**json.loads(line)))
    return out


def dedupe(examples: Iterable[Example]) -> list[Example]:
    """Keep the highest-weight row per (prompt, label), preferring real labels."""
    rank = {"human": 3, "outcome": 2, "claude-opus-5": 1, "taxonomy": 0}
    best: dict[str, Example] = {}
    for example in examples:
        key = example.prompt.strip().lower()
        current = best.get(key)
        if current is None or (
            (rank.get(example.label_source, 0), example.weight)
            > (rank.get(current.label_source, 0), current.weight)
        ):
            best[key] = example
    return list(best.values())


def _bucket(group: str, salt: str = "ccrouter") -> float:
    digest = hashlib.sha256(f"{salt}\x00{group}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def split(
    examples: Iterable[Example],
    val_frac: float = 0.15,
    test_frac: float = 0.15,
) -> dict[str, list[Example]]:
    """Deterministic, group-aware, source-aware split.

    The fractions apply only to rows that are eligible for every split; seed
    rows go entirely to train and golden rows entirely to test regardless.
    """
    if not 0 <= val_frac + test_frac < 1:
        raise ValueError("val_frac + test_frac must be in [0, 1)")

    out: dict[str, list[Example]] = {"train": [], "val": [], "test": []}
    for example in examples:
        if example.source in TRAIN_ONLY:
            out["train"].append(example)
        elif example.source in TEST_ONLY:
            out["test"].append(example)
        else:
            position = _bucket(example.group)
            if position < test_frac:
                out["test"].append(example)
            elif position < test_frac + val_frac:
                out["val"].append(example)
            else:
                out["train"].append(example)
    return out


def describe(examples: Iterable[Example]) -> str:
    rows = list(examples)
    if not rows:
        return "(empty)"
    labels = Counter(e.label for e in rows)
    sources = Counter(e.source for e in rows)
    label_sources = Counter(e.label_source for e in rows)
    parts = [
        f"{len(rows)} rows",
        "  labels:        " + ", ".join(f"{k}={labels[k]}" for k in TIERS),
        "  sources:       " + ", ".join(f"{k}={v}" for k, v in sources.most_common()),
        "  label sources: " + ", ".join(f"{k}={v}" for k, v in label_sources.most_common()),
        f"  mean weight:   {sum(e.weight for e in rows) / len(rows):.2f}",
        f"  groups:        {len({e.group for e in rows})}",
    ]
    return "\n".join(parts)


def iter_prompts(examples: Iterable[Example]) -> Iterator[str]:
    for example in examples:
        yield example.prompt
