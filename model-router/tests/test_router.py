"""Turn stickiness: choose once per human turn, escalate freely, never fall back."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ccrouter import config, router
from ccrouter.config import HAIKU, OPUS, SONNET

SYSTEM = "You are Claude Code, Anthropic's official CLI for Claude."
TOOLS = [{"name": n} for n in ("Task", "Bash", "Read", "Edit", "Write")]

CHEAP = "show me what does parse do in src/app.py"
READ = [{"type": "tool_use", "id": "1", "name": "Read", "input": {"file_path": "src/app.py"}}]
FAILED = [{"type": "tool_result", "content": "Traceback (most recent call last)\n2 tests failed"}]
RAN = [{"type": "tool_use", "id": "2", "name": "Bash", "input": {"command": "pytest"}}]


class StickinessTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        cfg = config.replace(config.load(), log_file=str(Path(self.tmp.name) / "log.jsonl"))
        self.router = router.Router(cfg)

    def decide(self, messages, model="claude-opus-5"):
        return self.router.decide(
            {"model": model, "system": SYSTEM, "tools": TOOLS, "messages": messages})

    def test_a_cheap_turn_routes_cheap_and_rewrites_the_model(self):
        decision = self.decide([{"role": "user", "content": CHEAP}])
        self.assertEqual(decision.tier, HAIKU)
        self.assertTrue(decision.rewrote)
        self.assertEqual(decision.model, "claude-haiku-4-5-20251001")

    def test_the_loop_escalates_when_tool_calls_start_failing(self):
        turn = [{"role": "user", "content": CHEAP}]
        self.assertEqual(self.decide(turn).tier, HAIKU)

        turn += [{"role": "assistant", "content": RAN},
                 {"role": "user", "content": FAILED},
                 {"role": "assistant", "content": RAN},
                 {"role": "user", "content": FAILED}]
        escalated = self.decide(turn)
        self.assertGreaterEqual(escalated.tier, SONNET)
        self.assertEqual(escalated.source, "escalation")

    def test_it_never_drops_back_down_inside_the_same_turn(self):
        turn = [{"role": "user", "content": CHEAP},
                {"role": "assistant", "content": RAN},
                {"role": "user", "content": FAILED},
                {"role": "assistant", "content": RAN},
                {"role": "user", "content": FAILED}]
        raised = self.decide(turn).tier

        # A quiet read-only step later in the same turn looks cheap in isolation.
        turn += [{"role": "assistant", "content": READ},
                 {"role": "user", "content": [{"type": "tool_result", "content": "ok"}]},
                 {"role": "assistant", "content": READ},
                 {"role": "user", "content": [{"type": "tool_result", "content": "ok"}]},
                 {"role": "assistant", "content": READ},
                 {"role": "user", "content": [{"type": "tool_result", "content": "ok"}]}]
        self.assertGreaterEqual(self.decide(turn).tier, raised)

    def test_a_new_human_turn_gets_a_fresh_decision(self):
        turn = [{"role": "user", "content": "design the sharding scheme"}]
        self.assertEqual(self.decide(turn).tier, OPUS)

        turn += [{"role": "assistant", "content": [{"type": "text", "text": "done"}]},
                 {"role": "user", "content": CHEAP}]
        fresh = self.decide(turn)
        self.assertEqual(fresh.tier, HAIKU)
        self.assertEqual(fresh.turn_index, 2)

    def test_two_conversations_do_not_share_a_decision(self):
        self.decide([{"role": "user", "content": "design the sharding scheme"}])
        other = self.decide([{"role": "user", "content": CHEAP}])
        self.assertEqual(other.tier, HAIKU)

    def test_background_haiku_calls_are_left_alone(self):
        decision = self.router.decide({
            "model": "claude-haiku-4-5-20251001", "system": "",
            "messages": [{"role": "user", "content": "Write a 5-word title for this chat"}]})
        self.assertFalse(decision.rewrote)
        self.assertEqual(decision.source, "passthrough")

    def test_every_decision_is_written_to_the_log(self):
        self.decide([{"role": "user", "content": CHEAP}])
        lines = Path(self.router._log_path).read_text().strip().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertIn("haiku", lines[0])

    def test_savings_are_reported_against_the_ceiling_tier(self):
        self.decide([{"role": "user", "content": CHEAP}])
        report = self.router.savings()
        self.assertGreater(report["estimated_saving_usd"], 0)
        self.assertIn("haiku", report["by_tier"])


if __name__ == "__main__":
    unittest.main()
