"""The routing decisions that matter, stated as the behaviour we want."""

from __future__ import annotations

import unittest

from ccrouter import config, rules, signals
from ccrouter.config import HAIKU, OPUS, SONNET

CFG = config.load()
SYSTEM = "You are Claude Code, Anthropic's official CLI for Claude."
TOOLS = [{"name": n} for n in ("Task", "Bash", "Read", "Edit", "Write", "Glob", "Grep")]


def route(messages, **body):
    payload = {"model": "claude-sonnet-5", "system": SYSTEM, "tools": TOOLS,
               "messages": messages, **body}
    return rules.evaluate(signals.extract(payload, CFG), CFG)


def ask(text, **body):
    return route([{"role": "user", "content": text}], **body)


class TestIntent(unittest.TestCase):
    def test_mechanical_single_file_work_goes_cheap(self):
        self.assertEqual(ask("rename the parse function in src/app.py").tier, HAIKU)

    def test_reading_and_summarising_goes_cheap(self):
        self.assertEqual(ask("show me what does handle_request do in src/http.py").tier, HAIKU)

    def test_design_work_goes_to_the_top_tier(self):
        self.assertEqual(ask("design the retry and backoff strategy for the queue").tier, OPUS)

    def test_debugging_something_not_understood_goes_to_the_top_tier(self):
        self.assertEqual(
            ask("why does the scheduler intermittently deadlock under load?").tier, OPUS)

    def test_ordinary_feature_work_lands_in_the_middle(self):
        self.assertEqual(ask("add a --json flag to the export command").tier, SONNET)


class TestBlastRadius(unittest.TestCase):
    def test_whole_codebase_wording_escalates(self):
        cheap = ask("update the changelog")
        broad = ask("update the changelog across the codebase")
        self.assertLess(cheap.score, broad.score)

    def test_many_files_escalates_above_one_file(self):
        one = ask("add a docstring to src/a.py")
        many = ask("add a docstring to src/a.py, src/b.py, src/c.py and src/d.py")
        self.assertLess(one.score, many.score)

    def test_enumerated_multi_step_work_escalates(self):
        verdict = ask("do this:\n1. add the flag\n2. wire it up\n3. write the tests\n4. update docs")
        self.assertIn("multi_step", [c.rule for c in verdict.contributions])


class TestLoopShape(unittest.TestCase):
    """The conversation's shape, not its length, is the strongest signal."""

    def test_a_readonly_followup_step_is_cheap(self):
        verdict = route([
            {"role": "user", "content": "explain the caching layer and its trade-offs"},
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "1", "name": "Read", "input": {"file_path": "cache.py"}}]},
            {"role": "user", "content": [{"type": "tool_result", "content": "class Cache: ..."}]},
        ])
        self.assertIn("readonly_followup", [c.rule for c in verdict.contributions])

    def test_a_readonly_bash_command_still_counts_as_readonly(self):
        verdict = route([
            {"role": "user", "content": "what is in the config?"},
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "1", "name": "Bash", "input": {"command": "cat cfg.toml"}}]},
            {"role": "user", "content": [{"type": "tool_result", "content": "port = 4000"}]},
        ])
        self.assertIn("readonly_followup", [c.rule for c in verdict.contributions])

    def test_failing_tool_results_raise_the_floor(self):
        verdict = route([
            {"role": "user", "content": "run the tests"},
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "1", "name": "Bash", "input": {"command": "pytest"}}]},
            {"role": "user", "content": [{"type": "tool_result", "content": "3 tests failed"}]},
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "2", "name": "Bash", "input": {"command": "pytest -x"}}]},
            {"role": "user", "content": [
                {"type": "tool_result", "content": "Traceback (most recent call last)"}]},
        ])
        self.assertGreaterEqual(verdict.tier, SONNET)

    def test_an_explicit_error_flag_counts_even_without_a_known_pattern(self):
        verdict = route([
            {"role": "user", "content": "run it"},
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "1", "name": "Bash", "input": {"command": "./x"}}]},
            {"role": "user", "content": [
                {"type": "tool_result", "is_error": True, "content": "nope"}]},
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "2", "name": "Bash", "input": {"command": "./x"}}]},
            {"role": "user", "content": [
                {"type": "tool_result", "is_error": True, "content": "nope"}]},
        ])
        self.assertGreaterEqual(verdict.tier, SONNET)

    def test_repeating_the_same_tool_call_is_treated_as_thrash(self):
        same = {"type": "tool_use", "id": "1", "name": "Bash", "input": {"command": "make"}}
        verdict = route([
            {"role": "user", "content": "build it"},
            {"role": "assistant", "content": [same]},
            {"role": "user", "content": [{"type": "tool_result", "content": "ok"}]},
            {"role": "assistant", "content": [dict(same, id="2")]},
            {"role": "user", "content": [{"type": "tool_result", "content": "ok"}]},
        ])
        self.assertIn("tool_thrash", [c.rule for c in verdict.contributions])


class TestFloorsAndPins(unittest.TestCase):
    def test_extended_thinking_is_never_downgraded(self):
        verdict = ask("read src/app.py", thinking={"type": "enabled", "budget_tokens": 30000})
        self.assertEqual(verdict.tier, OPUS)

    def test_a_huge_context_keeps_us_off_the_small_model(self):
        verdict = ask("summarise this\n" + "x " * 60_000)
        self.assertGreaterEqual(verdict.tier, SONNET)

    def test_the_user_can_pin_a_tier_from_the_prompt(self):
        self.assertEqual(ask("!opus rename the parse function in src/app.py").tier, OPUS)
        self.assertEqual(ask("design the whole auth system !haiku").tier, HAIKU)

    def test_a_configured_ceiling_is_respected(self):
        cfg = config.replace(CFG, policy=config.replace(CFG.policy, max_tier="sonnet"))
        payload = {"model": "claude-sonnet-5", "system": SYSTEM, "tools": TOOLS,
                   "messages": [{"role": "user", "content": "design a distributed scheduler"}]}
        self.assertEqual(rules.evaluate(signals.extract(payload, cfg), cfg).tier, SONNET)

    def test_a_pasted_stack_trace_escalates(self):
        plain = ask("fix the importer in src/load.py")
        traced = ask("fix the importer in src/load.py\n\nTraceback (most recent call last)\n"
                     "  File \"src/load.py\", line 9\nKeyError: 'id'")
        self.assertLess(plain.score, traced.score)


class TestSubagents(unittest.TestCase):
    def test_a_search_subagent_routes_cheap(self):
        payload = {"model": "claude-sonnet-5", "tools": [{"name": "Grep"}, {"name": "Read"}],
                   "system": "You are the Explore agent for Claude Code.",
                   "messages": [{"role": "user", "content": "find every caller of load_config"}]}
        verdict = rules.evaluate(signals.extract(payload, CFG), CFG)
        self.assertEqual(verdict.tier, HAIKU)


class TestExplainability(unittest.TestCase):
    def test_every_decision_carries_its_reasons(self):
        for verdict in (ask("read src/a.py"), ask("design the sharding scheme")):
            self.assertTrue(verdict.reasons)
            self.assertTrue(all(isinstance(r, str) and r.strip() for r in verdict.reasons))


if __name__ == "__main__":
    unittest.main()
