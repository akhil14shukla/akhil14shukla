"""The semantic scorer, and the promise that it is optional.

Everything that needs numpy is skipped when numpy is absent, because the router
must keep working with nothing but the standard library installed.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from ccrouter import config, rules, semantic, signals
from ccrouter.config import HAIKU, OPUS, SONNET

SYSTEM = "You are Claude Code, Anthropic's official CLI for Claude."
TOOLS = [{"name": n} for n in ("Task", "Bash", "Read", "Edit", "Write")]
MODEL_PATH = Path(__file__).resolve().parents[1] / "ml" / "dataset" / "model.npz"

try:
    import numpy  # noqa: F401
    from model2vec import StaticModel  # noqa: F401

    HAVE_DEPS = True
except ImportError:
    HAVE_DEPS = False


def sig(prompt: str, cfg):
    return signals.extract(
        {"model": "claude-sonnet-5", "system": SYSTEM, "tools": TOOLS,
         "messages": [{"role": "user", "content": prompt}]}, cfg)


class FeatureOrderTest(unittest.TestCase):
    """Training and serving must agree on the feature order or nothing works."""

    def test_the_vector_matches_the_declared_key_order(self):
        vector = semantic.structural_vector({"phase": "tool_loop", "failures": 3}, "hi")
        self.assertEqual(len(vector), len(semantic.STRUCTURAL_KEYS))
        keys = semantic.STRUCTURAL_KEYS
        self.assertEqual(vector[keys.index("is_tool_loop")], 1.0)
        self.assertEqual(vector[keys.index("is_user_turn")], 0.0)
        self.assertEqual(vector[keys.index("failures")], 3.0)

    def test_missing_signals_read_as_zero_not_as_an_error(self):
        vector = semantic.structural_vector({})
        self.assertEqual(len(vector), len(semantic.STRUCTURAL_KEYS))
        self.assertEqual(vector[semantic.STRUCTURAL_KEYS.index("is_user_turn")], 1.0)

    def test_a_signals_object_projects_onto_the_same_keys(self):
        cfg = config.load()
        projected = semantic.signals_dict(sig("read src/a.py and fix the typo", cfg))
        self.assertEqual(projected["phase"], "user_turn")
        self.assertIn("files_mentioned", projected)
        self.assertEqual(len(semantic.structural_vector(projected)),
                         len(semantic.STRUCTURAL_KEYS))

    def test_a_garbage_signal_value_does_not_raise(self):
        vector = semantic.structural_vector({"failures": None, "context_tokens": "lots"})
        self.assertEqual(len(vector), len(semantic.STRUCTURAL_KEYS))


class UnavailableTest(unittest.TestCase):
    """Absent model, absent numpy, absent everything: the router still routes."""

    def test_a_missing_model_file_reports_unavailable_and_does_not_raise(self):
        scorer = semantic.Scorer("/nonexistent/model.npz")
        self.assertFalse(scorer.available)
        self.assertIn("no model", scorer.error)
        self.assertIsNone(scorer.predict("anything"))

    def test_scoring_is_skipped_entirely_when_disabled(self):
        cfg = config.load()
        self.assertFalse(cfg.semantic.enabled)
        self.assertIsNone(semantic.score_for("read src/a.py", sig("read src/a.py", cfg), cfg))

    def test_an_enabled_but_missing_model_falls_through_to_rules(self):
        base = config.load()
        cfg = config.replace(base, semantic=config.replace(
            base.semantic, enabled=True, model_path="/nonexistent/model.npz"))
        prompt = "rename parse in src/app.py"
        self.assertIsNone(semantic.score_for(prompt, sig(prompt, cfg), cfg))
        self.assertEqual(rules.evaluate(sig(prompt, cfg), cfg).tier, HAIKU)


class FusionTest(unittest.TestCase):
    """The model votes; it does not rule."""

    def setUp(self):
        self.cfg = config.load()

    def test_a_semantic_vote_can_move_the_tier(self):
        prompt = "rename parse in src/app.py"
        plain = rules.evaluate(sig(prompt, self.cfg), self.cfg)
        pushed = rules.evaluate(sig(prompt, self.cfg), self.cfg,
                                semantic=(1.2, "opus p=0.99"))
        self.assertEqual(plain.tier, HAIKU)
        self.assertGreater(pushed.tier, plain.tier)
        self.assertIn("semantic_model", [c.rule for c in pushed.contributions])

    def test_a_semantic_vote_cannot_undercut_a_floor(self):
        prompt = "design the sharding scheme"
        verdict = rules.evaluate(
            sig(prompt, self.cfg), self.cfg,
            semantic=(-1.5, "haiku p=0.99"),   # model is confidently wrong
        )
        # Thinking is off here, so the floor that holds is the failure/context one;
        # what must never happen is the model dragging a thinking request down.
        thinking = signals.extract(
            {"model": "claude-sonnet-5", "system": SYSTEM, "tools": TOOLS,
             "thinking": {"type": "enabled", "budget_tokens": 30000},
             "messages": [{"role": "user", "content": prompt}]}, self.cfg)
        floored = rules.evaluate(thinking, self.cfg, semantic=(-1.5, "haiku p=0.99"))
        self.assertEqual(floored.tier, OPUS)
        self.assertLessEqual(verdict.tier, OPUS)

    def test_a_user_override_still_beats_the_model(self):
        prompt = "!haiku design the whole authentication system"
        verdict = rules.evaluate(sig(prompt, self.cfg), self.cfg,
                                 semantic=(1.5, "opus p=0.99"))
        self.assertEqual(verdict.tier, HAIKU)
        self.assertEqual(verdict.source, "override")


@unittest.skipUnless(HAVE_DEPS, "numpy/model2vec not installed")
@unittest.skipUnless(MODEL_PATH.is_file(), "no trained model; run ml/train.py")
class TrainedModelTest(unittest.TestCase):
    def setUp(self):
        base = config.load()
        self.cfg = config.replace(base, semantic=config.replace(
            base.semantic, enabled=True, model_path=str(MODEL_PATH)))
        self.scorer = semantic.get(str(MODEL_PATH), "")

    def test_the_exported_model_loads(self):
        self.assertTrue(self.scorer.available, self.scorer.error)

    def test_probabilities_are_a_distribution_over_the_tiers(self):
        prediction = self.scorer.predict("read src/app.py")
        self.assertIsNotNone(prediction)
        self.assertEqual(set(prediction.probabilities), {"haiku", "sonnet", "opus"})
        self.assertAlmostEqual(sum(prediction.probabilities.values()), 1.0, places=5)

    def test_it_separates_a_minimal_pair_the_lexicon_cannot(self):
        cheap = self.scorer.predict("rename OrderService to OrderRecord in app/models.rb")
        hard = self.scorer.predict(
            "rename OrderService to OrderRecord everywhere and keep the public API compatible")
        self.assertLess(cheap.margin, hard.margin)
        self.assertEqual(cheap.tier, "haiku")
        self.assertEqual(hard.tier, "opus")

    def test_fusion_rescues_a_prompt_the_rules_under_route(self):
        prompt = "read src/queue.go and work out why prod diverges from staging"
        s = sig(prompt, self.cfg)
        plain = rules.evaluate(s, self.cfg)
        fused = rules.evaluate(s, self.cfg, semantic=semantic.score_for(prompt, s, self.cfg))
        self.assertEqual(plain.tier, HAIKU)       # "read" matched the cheap lexicon
        self.assertGreaterEqual(fused.tier, SONNET)

    def test_an_empty_prompt_yields_no_prediction(self):
        self.assertIsNone(self.scorer.predict("   "))


if __name__ == "__main__":
    unittest.main()
