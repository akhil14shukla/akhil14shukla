#!/usr/bin/env python3
"""Check the structural invariants this skill suite depends on.

Progressive disclosure only works if the routing is honest: every path a
SKILL.md names must exist, every bundled file must be reachable from some
routing table, and no core may quietly grow past its budget. This checks all
of that, so a broken pointer is caught here rather than by a model mid-task.

    python validate.py            # check, exit 1 on any problem
    python validate.py --quiet    # only print problems
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

CORE_BUDGET_CHARS = 6200  # ~1,550 tokens
SPEC_FIELDS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
CLAUDE_CODE_FIELDS = {
    "when_to_use", "argument-hint", "disable-model-invocation",
    "disallowed-tools", "paths", "context", "arguments",
}
DESCRIPTION_CAP = 1536  # description + when_to_use, per the skill listing


def parse_frontmatter(text: str) -> tuple[dict[str, str], str] | None:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if m is None:
        return None
    fields: dict[str, str] = {}
    key: str | None = None
    for line in m.group(1).split("\n"):
        km = re.match(r"^([a-zA-Z][\w-]*):\s*(.*)$", line)
        if km:
            key = km.group(1)
            fields[key] = km.group(2)
        elif key and line.strip():
            fields[key] += " " + line.strip()
    return fields, text[m.end() :]


def check(skills_dir: Path) -> list[str]:
    problems: list[str] = []
    skill_names = {p.parent.name for p in skills_dir.glob("*/SKILL.md")}
    if not skill_names:
        return [f"no skills found in {skills_dir}"]

    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        d = skill_md.parent
        name = d.name
        parsed = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
        if parsed is None:
            problems.append(f"{name}: SKILL.md has no YAML frontmatter")
            continue
        fields, body = parsed

        for key in fields:
            if key not in SPEC_FIELDS | CLAUDE_CODE_FIELDS:
                problems.append(f"{name}: unknown frontmatter field {key!r}")
        if fields.get("name") != name:
            problems.append(f"{name}: frontmatter name is {fields.get('name')!r}, not the directory name")
        if not fields.get("description"):
            problems.append(f"{name}: no description — the skill will rarely trigger")
        listing = len(fields.get("description", "")) + len(fields.get("when_to_use", ""))
        if listing > DESCRIPTION_CAP:
            problems.append(f"{name}: description+when_to_use is {listing} chars, over the {DESCRIPTION_CAP} cap")

        if len(body) > CORE_BUDGET_CHARS:
            problems.append(
                f"{name}: core is {len(body)} chars (~{len(body) // 4} tokens), over budget — "
                "move task-specific material into references/ and route to it"
            )
        if "| Read |" not in body:
            problems.append(f"{name}: core has no routing table, so its references are unreachable")

        # Every path the core names must exist. A trailing-slash path is a
        # directory of per-variant files, and must be a non-empty directory.
        # Paths appear both inline in backticks and inside bash examples, so match
        # them bare. The trailing [\w/] stops a sentence's full stop being swallowed
        # into the path.
        routed = set(re.findall(r"(?:references|scripts|assets)/[\w./-]*[\w/]", body))
        for ref in sorted(routed):
            target = d / ref
            if ref.endswith("/"):
                if not target.is_dir() or not any(target.iterdir()):
                    problems.append(f"{name}: routes to `{ref}` which is not a non-empty directory")
            elif not target.exists():
                problems.append(f"{name}: routes to `{ref}` which does not exist")

        # Every bundled file must be reachable from the routing table: either its
        # own path is routed, or it sits in a per-variant directory that is.
        # Match against the routed set, not the raw body — "references/" occurs as
        # a substring of every reference path and would excuse anything.
        for f in sorted(d.rglob("*")):
            if not f.is_file() or f.name == "SKILL.md":
                continue
            rel = f.relative_to(d).as_posix()
            parent = f.parent.relative_to(d).as_posix() + "/"
            if rel not in routed and parent not in routed:
                problems.append(f"{name}: {rel} is never routed to — dead weight")

    # A skill mentioned by another skill must exist.
    for md in sorted(skills_dir.rglob("*.md")):
        for mention in re.findall(r"`([a-z]+-[a-z]+)`", md.read_text(encoding="utf-8")):
            if mention.endswith(("-craft", "-engineering", "-architect", "-quality", "-recon")):
                if mention not in skill_names:
                    problems.append(f"{md.relative_to(skills_dir)}: mentions unknown skill {mention!r}")

    # Unbalanced code fences render as one giant code block.
    for md in sorted(skills_dir.rglob("*.md")):
        text = md.read_text(encoding="utf-8")
        if (text.count("\n```") + (1 if text.startswith("```") else 0)) % 2:
            problems.append(f"{md.relative_to(skills_dir)}: unbalanced code fences")

    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dir", default=None, help="Skills directory (default: this file's own)")
    parser.add_argument("--quiet", action="store_true", help="Print only problems")
    args = parser.parse_args(argv)

    skills_dir = Path(args.dir).resolve() if args.dir else Path(__file__).resolve().parent
    problems = check(skills_dir)

    if problems:
        print(f"{len(problems)} problem(s) in {skills_dir}:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    if not args.quiet:
        n = len(list(skills_dir.glob("*/SKILL.md")))
        print(f"{n} skills valid: frontmatter, routing, budgets, and cross-references all check out.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
