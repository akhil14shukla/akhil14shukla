"""Turn a raw /v1/messages request body into the features the rules vote on.

Everything here is derived from what Claude Code already puts on the wire: the
conversation shape, the tools in flight, and what the last few tool calls did.
That is a far richer signal than the length of the prompt.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

from .config import Config

_SYSTEM_REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
_CODE_FENCE = re.compile(r"```.*?```", re.S)
_PATH = re.compile(r"\b[\w.\-/]+\.(?:py|ts|tsx|js|jsx|go|rs|java|rb|php|c|h|cpp|hpp|cs|kt|swift|sh|sql|md|json|toml|yaml|yml|html|css)\b")
_DIRPATH = re.compile(r"\b(?:src|lib|app|pkg|internal|tests?|cmd)/[\w.\-/]+")
_BROAD = re.compile(r"\*\*?/|\ball (?:the )?files\b|\bacross the (?:codebase|repo\w*|project)\b|\bevery(?:where| file| module| package)\b|\bwhole (?:codebase|repo\w*|project)\b", re.I)
_STEP = re.compile(r"^\s*(?:\d+[.)]|[-*])\s+", re.M)
_AND_THEN = re.compile(r"\band then\b|\bafter that\b|\bfinally,", re.I)
_PRONOUN_ONLY = re.compile(r"^\s*(?:now |ok |okay )?(?:please )?(?:fix|do|try|continue|redo|change|handle|apply)\s+(?:it|that|this|those|them)\b", re.I)
_QUESTION = re.compile(r"^\s*(?:what|where|which|who|when|does|do|is|are|can|how many)\b", re.I)
_OVERRIDE = re.compile(r"(?:^|\s)(?:!|\[\[)(haiku|sonnet|opus)(?:\]\])?(?:\s|$)", re.I)

# Bash invocations that only observe. Used to tell a "look" step from a "change" step.
_READONLY_BASH = re.compile(r"^\s*(?:cat|ls|head|tail|wc|grep|rg|find|git (?:log|show|diff|status|branch)|pwd|which|echo|stat|file|tree|jq|sed -n)\b")


def _blocks(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return [b for b in content if isinstance(b, dict)]
    return []


def _text_of(content: Any) -> str:
    return "\n".join(b.get("text", "") for b in _blocks(content) if b.get("type") == "text")


def _system_text(body: dict[str, Any]) -> str:
    system = body.get("system")
    if isinstance(system, str):
        return system
    if isinstance(system, list):
        return "\n".join(b.get("text", "") for b in system if isinstance(b, dict))
    return ""


def _is_tool_result_turn(message: dict[str, Any]) -> bool:
    return any(b.get("type") == "tool_result" for b in _blocks(message.get("content")))


def _clean_prompt(text: str) -> str:
    return _SYSTEM_REMINDER.sub(" ", text).strip()


@dataclass(frozen=True)
class Signals:
    """Everything the rule engine is allowed to look at."""

    session_key: str = ""
    turn_index: int = 0
    phase: str = "user_turn"          # user_turn | tool_loop | unknown
    requested_model: str = ""
    is_subagent: bool = False
    agent_hint: str = ""

    prompt: str = ""
    prompt_chars: int = 0
    override_tier: str = ""

    thinking_budget: int = 0
    context_tokens: int = 0
    n_messages: int = 0

    tool_names: tuple[str, ...] = ()
    recent_tools: tuple[str, ...] = ()
    recent_tools_readonly: bool = False

    failures: int = 0
    thrash: int = 0

    files_mentioned: int = 0
    broad_scope: bool = False
    enumerated_steps: int = 0
    has_stacktrace: bool = False
    is_question: bool = False
    underspecified: bool = False

    matched_cheap: tuple[str, ...] = field(default=())
    matched_expensive: tuple[str, ...] = field(default=())


def _estimate_tokens(body: dict[str, Any]) -> int:
    try:
        return len(json.dumps(body, default=str)) // 4
    except (TypeError, ValueError):
        return 0


def _last_human_message(messages: list[dict[str, Any]]) -> tuple[str, int]:
    """Return the newest genuine human instruction and how many such turns exist."""
    human_turns = [
        m for m in messages
        if m.get("role") == "user" and not _is_tool_result_turn(m)
    ]
    if not human_turns:
        return "", 0
    return _clean_prompt(_text_of(human_turns[-1].get("content"))), len(human_turns)


def _recent_tool_use(messages: list[dict[str, Any]], depth: int = 3) -> list[dict[str, Any]]:
    uses: list[dict[str, Any]] = []
    for message in reversed(messages):
        if message.get("role") != "assistant":
            continue
        uses = [b for b in _blocks(message.get("content")) if b.get("type") == "tool_use"] + uses
        depth -= 1
        if depth <= 0:
            break
    return uses


def _count_failures(messages: list[dict[str, Any]], patterns: tuple[str, ...], depth: int) -> int:
    joined = re.compile("|".join(patterns)) if patterns else None
    if joined is None:
        return 0
    failures = 0
    for message in [m for m in messages if m.get("role") == "user"][-depth:]:
        for block in _blocks(message.get("content")):
            if block.get("type") != "tool_result":
                continue
            if block.get("is_error"):
                failures += 1
                continue
            if joined.search(_text_of(block.get("content"))[:8000]):
                failures += 1
    return failures


def _count_thrash(uses: list[dict[str, Any]]) -> int:
    """How many times the most-repeated identical tool call appears. Loop detector."""
    seen: dict[str, int] = {}
    for use in uses[-8:]:
        key = hashlib.sha1(
            json.dumps([use.get("name"), use.get("input")], sort_keys=True, default=str).encode()
        ).hexdigest()
        seen[key] = seen.get(key, 0) + 1
    return max(seen.values(), default=0)


def _bash_is_readonly(use: dict[str, Any]) -> bool:
    command = str((use.get("input") or {}).get("command", ""))
    first = command.split("&&")[0].split("|")[0]
    return bool(_READONLY_BASH.match(first))


def extract(body: dict[str, Any], cfg: Config) -> Signals:
    messages = [m for m in body.get("messages", []) if isinstance(m, dict)]
    system = _system_text(body)
    prompt, turn_index = _last_human_message(messages)

    phase = "unknown"
    if messages:
        last = messages[-1]
        if last.get("role") == "user":
            phase = "tool_loop" if _is_tool_result_turn(last) else "user_turn"
        else:
            phase = "tool_loop"

    tool_names = tuple(
        str(t.get("name", "")) for t in body.get("tools", []) if isinstance(t, dict)
    )
    uses = _recent_tool_use(messages)
    recent = tuple(str(u.get("name", "")) for u in uses)
    readonly = set(cfg.readonly_tools)
    recent_readonly = bool(recent) and all(
        name in readonly or (name == "Bash" and _bash_is_readonly(use))
        for name, use in zip(recent, uses)
    )

    thinking = body.get("thinking") or {}
    budget = int(thinking.get("budget_tokens", 0)) if thinking.get("type") == "enabled" else 0

    body_text = prompt
    stripped = _CODE_FENCE.sub(" ", body_text)
    files = set(_PATH.findall(stripped)) | set(_DIRPATH.findall(stripped))

    override = ""
    match = _OVERRIDE.search(prompt)
    if match:
        override = match.group(1).lower()

    is_subagent = any(re.search(m, system, re.I) for m in cfg.subagent_markers) or (
        bool(tool_names) and "Task" not in tool_names and "Agent" not in tool_names
    )
    agent_hint = ""
    hint = re.search(r"You are (?:the |a |an )?([\w-]+) (?:agent|subagent)", system, re.I)
    if hint:
        agent_hint = hint.group(1).lower()

    matched_cheap = tuple(p for p in cfg.cheap_lexicon if re.search(p, stripped, re.I))
    matched_expensive = tuple(p for p in cfg.expensive_lexicon if re.search(p, stripped, re.I))

    first_human = next(
        (_text_of(m.get("content")) for m in messages if m.get("role") == "user" and not _is_tool_result_turn(m)),
        "",
    )
    session_key = hashlib.sha1(
        (system[:512] + "\x00" + first_human[:512]).encode("utf-8", "replace")
    ).hexdigest()[:16]

    return Signals(
        session_key=session_key,
        turn_index=turn_index,
        phase=phase,
        requested_model=str(body.get("model", "")),
        is_subagent=is_subagent,
        agent_hint=agent_hint,
        prompt=prompt,
        prompt_chars=len(prompt),
        override_tier=override,
        thinking_budget=budget,
        context_tokens=_estimate_tokens(body),
        n_messages=len(messages),
        tool_names=tool_names,
        recent_tools=recent,
        recent_tools_readonly=recent_readonly,
        failures=_count_failures(messages, cfg.failure_patterns, depth=6),
        thrash=_count_thrash(uses),
        files_mentioned=len(files),
        broad_scope=bool(_BROAD.search(prompt)),
        enumerated_steps=len(_STEP.findall(prompt)) + len(_AND_THEN.findall(prompt)),
        has_stacktrace=bool(re.search(r"Traceback \(most recent call last\)|\bat [\w.$]+\(.*:\d+\)|error TS\d+", prompt)),
        is_question=bool(_QUESTION.match(prompt)),
        underspecified=bool(_PRONOUN_ONLY.match(prompt)) or (0 < len(prompt) < 40 and not files),
        matched_cheap=matched_cheap,
        matched_expensive=matched_expensive,
    )
