#!/usr/bin/env python3
"""Report what this skill suite costs in context, by disclosure level.

Skills are only cheap if someone keeps them cheap. This measures the three
levels so a core that has quietly grown is visible before it costs anything:

    level 1  descriptions      always in context, for every session
    level 2  SKILL.md bodies   loaded when a skill triggers, and stays
    level 3  references        loaded only when a routing table points at one

    python context_cost.py                 # summary
    python context_cost.py --detail        # per reference file too
    python context_cost.py --budget 1200   # fail if any core exceeds the budget

Token counts are estimates (~4 characters per token for prose and code). They
are for comparing files and spotting growth, not for billing.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

CHARS_PER_TOKEN = 4
DEFAULT_CORE_BUDGET = 1500


@dataclass(frozen=True, slots=True)
class Skill:
    name: str
    description: str
    core: str
    references: dict[str, str]

    @property
    def core_tokens(self) -> int:
        return len(self.core) // CHARS_PER_TOKEN

    @property
    def description_tokens(self) -> int:
        return len(self.description) // CHARS_PER_TOKEN

    @property
    def reference_tokens(self) -> int:
        return sum(len(t) for t in self.references.values()) // CHARS_PER_TOKEN

    @property
    def heaviest_reference(self) -> int:
        """Worst-case level-3 cost: the largest single file a router can select."""
        return max((len(t) for t in self.references.values()), default=0) // CHARS_PER_TOKEN


def load(skills_dir: Path) -> list[Skill]:
    skills = []
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        text = skill_md.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        if m is None:
            print(f"warning: {skill_md} has no frontmatter; skipped", file=sys.stderr)
            continue
        frontmatter, core = m.group(1), text[m.end() :]
        desc = re.search(r"^description:\s*(.*?)(?=\n[a-zA-Z_-]+:|\Z)", frontmatter, re.S | re.M)
        refs = {
            str(p.relative_to(skill_md.parent / "references")): p.read_text(encoding="utf-8")
            for p in sorted((skill_md.parent / "references").rglob("*.md"))
        }
        skills.append(
            Skill(
                name=skill_md.parent.name,
                description=" ".join(desc.group(1).split()) if desc else "",
                core=core,
                references=refs,
            )
        )
    return skills


def report(skills: list[Skill], *, detail: bool, budget: int) -> int:
    if not skills:
        print("No skills found.", file=sys.stderr)
        return 1

    print(f"{'skill':<20}{'desc':>7}{'core':>8}{'refs':>8}{'worst ref':>11}")
    print("-" * 54)
    for s in sorted(skills, key=lambda s: -s.core_tokens):
        flag = "  <-- over budget" if s.core_tokens > budget else ""
        print(
            f"{s.name:<20}{s.description_tokens:>7}{s.core_tokens:>8}"
            f"{s.reference_tokens:>8}{s.heaviest_reference:>11}{flag}"
        )
        if detail:
            for name, body in sorted(s.references.items(), key=lambda kv: -len(kv[1])):
                print(f"{'':<22}{name:<34}{len(body) // CHARS_PER_TOKEN:>6}")
    print("-" * 54)

    level1 = sum(s.description_tokens for s in skills)
    cores = sorted((s.core_tokens for s in skills), reverse=True)
    worst_ref = max(s.heaviest_reference for s in skills)

    print(f"\nLevel 1  always in context ({len(skills)} descriptions){level1:>18} tokens")
    print(f"Level 2  one core triggering{'':>21}{cores[0]:>8} worst, {cores[-1]:>4} best")
    print(f"Level 3  one reference read{'':>22}{worst_ref:>8} worst")

    typical = level1 + sum(cores[:2]) + worst_ref // 2
    everything = level1 + sum(cores) + sum(s.reference_tokens for s in skills)
    print(
        f"\nTypical session (2 cores + 1 reference){'':>3}{typical:>10} tokens"
        f"\nIf every skill loaded in full{'':>14}{everything:>10} tokens"
        f"  ({everything // max(typical, 1)}x more)"
    )

    over = [s for s in skills if s.core_tokens > budget]
    if over:
        print(f"\n{len(over)} core(s) over the {budget}-token budget:")
        for s in over:
            print(f"  {s.name}: {s.core_tokens}")
        print("\nMove task-specific material into references/ and route to it instead.")
        return 1
    print(f"\nAll cores within the {budget}-token budget.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dir", default=None, help="Skills directory (default: this file's own)")
    parser.add_argument("--detail", action="store_true", help="List every reference file")
    parser.add_argument(
        "--budget",
        type=int,
        default=DEFAULT_CORE_BUDGET,
        help=f"Per-core token budget; exit 1 if exceeded (default: {DEFAULT_CORE_BUDGET})",
    )
    args = parser.parse_args(argv)

    skills_dir = Path(args.dir).resolve() if args.dir else Path(__file__).resolve().parent
    if not skills_dir.is_dir():
        print(f"error: {skills_dir} is not a directory", file=sys.stderr)
        return 2
    return report(load(skills_dir), detail=args.detail, budget=args.budget)


if __name__ == "__main__":
    raise SystemExit(main())
