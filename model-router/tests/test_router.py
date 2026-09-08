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
        self.assertGreater(report["net_saving_usd"], 0)
        self.assertIn("haiku", report["by_tier"])
        self.assertIn("estimated", report["basis"])

    def test_savings_switch_to_measured_numbers_once_responses_arrive(self):
        decision = self.decide([{"role": "user", "content": CHEAP}])
        self.router.observe_usage(decision, {
            "input_tokens": 300, "output_tokens": 900,
            "cache_read_input_tokens": 40_000, "cache_creation_input_tokens": 1_200,
        })
        report = self.router.savings()
        self.assertIn("measured", report["basis"])
        self.assertEqual(report["measured_by_tier"]["haiku"]["cache_read"], 40_000)
        # Same tokens priced on haiku must beat the same tokens priced on opus.
        self.assertGreater(report["net_saving_usd"], 0)

    def test_the_savings_report_subtracts_what_re_warming_cost(self):
        self.decide([{"role": "user", "content": CHEAP}])
        naive = self.router.savings()["net_saving_usd"]
        self.router.rewarm_usd = 999.0
        self.assertLess(self.router.savings()["net_saving_usd"], naive)


class CacheGateTest(unittest.TestCase):
    """A switch throws away the warm prefix. It has to earn that back."""

    PAD = "x " * 100_000          # ~50k tokens of already-cached conversation

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = config.replace(
            config.load(), log_file=str(Path(self.tmp.name) / "log.jsonl"))

    def run_pair(self, first, second, cfg=None, pad=True):
        router_ = router.Router(cfg or self.base)
        head = [{"role": "user", "content": first}]
        a = router_.decide({"model": "claude-sonnet-5", "system": SYSTEM,
                            "tools": TOOLS, "messages": head})
        tail = head + ([{"role": "assistant", "content": [
            {"type": "text", "text": self.PAD}]}] if pad else [])
        tail = tail + [{"role": "user", "content": second}]
        b = router_.decide({"model": "claude-sonnet-5", "system": SYSTEM,
                            "tools": TOOLS, "messages": tail})
        return a, b, router_

    def test_an_unprofitable_downgrade_is_refused(self):
        first, second, _ = self.run_pair(
            "add a --json flag to the export command", "now show me src/export.py")
        self.assertEqual(first.tier, SONNET)
        self.assertEqual(second.tier, SONNET)          # would be haiku without the gate
        self.assertEqual(second.source, "cache_hold")
        self.assertIn("re-warm", " ".join(second.reasons))

    def test_a_downgrade_that_pays_is_allowed(self):
        # opus -> haiku saves far more per request, so it clears the re-warm.
        first, second, _ = self.run_pair(
            "design the sharding scheme for orders", "now show me src/export.py")
        self.assertEqual(first.tier, OPUS)
        self.assertEqual(second.tier, HAIKU)
        self.assertNotEqual(second.source, "cache_hold")

    def test_the_gate_can_be_turned_off(self):
        cfg = config.replace(self.base, policy=config.replace(
            self.base.policy, switch_must_pay_for_itself=False))
        _, second, _ = self.run_pair(
            "add a --json flag to the export command", "now show me src/export.py", cfg)
        self.assertEqual(second.tier, HAIKU)

    def test_a_small_context_lets_the_downgrade_through(self):
        _, second, _ = self.run_pair(
            "add a --json flag to the export command", "now show me src/export.py",
            pad=False)
        self.assertEqual(second.tier, HAIKU)

    def test_the_gate_never_blocks_an_upgrade(self):
        """Escalation is a quality decision; no cache saving outranks it."""
        cfg = self.base
        router_ = router.Router(cfg)
        head = [{"role": "user", "content": CHEAP}]
        router_.decide({"model": "claude-opus-5", "system": SYSTEM,
                        "tools": TOOLS, "messages": head})
        failing = head + [
            {"role": "assistant", "content": [
                {"type": "text", "text": self.PAD}]},
            {"role": "assistant", "content": RAN},
            {"role": "user", "content": FAILED},
            {"role": "assistant", "content": RAN},
            {"role": "user", "content": FAILED}]
        decision = router_.decide({"model": "claude-opus-5", "system": SYSTEM,
                                   "tools": TOOLS, "messages": failing})
        self.assertGreaterEqual(decision.tier, SONNET)
        self.assertNotEqual(decision.source, "cache_hold")

    def test_exploration_is_exempt_so_the_training_data_stays_unbiased(self):
        cfg = config.replace(self.base, policy=config.replace(
            self.base.policy, explore_rate=1.0))
        router_ = router.Router(cfg)
        router_._rng.seed(3)
        head = [{"role": "user", "content": "add a --json flag to the export command"}]
        router_.decide({"model": "claude-sonnet-5", "system": SYSTEM,
                        "tools": TOOLS, "messages": head})
        tail = head + [{"role": "assistant", "content": [
            {"type": "text", "text": self.PAD}]},
            {"role": "user", "content": "now show me src/export.py"}]
        decision = router_.decide({"model": "claude-sonnet-5", "system": SYSTEM,
                                   "tools": TOOLS, "messages": tail})
        self.assertEqual(decision.source, "explore")

    def test_re_warm_spend_is_accumulated(self):
        _, _, router_ = self.run_pair(
            "design the sharding scheme for orders", "now show me src/export.py")
        self.assertGreater(router_.rewarm_usd, 0)

    def test_turn_lengths_are_learned_from_traffic(self):
        _, _, router_ = self.run_pair(
            "design the sharding scheme for orders", "now show me src/export.py")
        self.assertGreaterEqual(router_._turn_length.samples, 1)


if __name__ == "__main__":
    unittest.main()
