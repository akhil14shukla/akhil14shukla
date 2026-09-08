"""The dataset contract: the split policy is the part that can silently lie."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ml"))

import golden  # noqa: E402
import seed as seed_module  # noqa: E402
from schema import TIERS, Example, dedupe, read, split, write  # noqa: E402


class ExampleTest(unittest.TestCase):
    def test_an_unknown_tier_is_rejected_at_construction(self):
        with self.assertRaises(ValueError):
            Example(prompt="x", label="gpt", source="seed")

    def test_an_empty_prompt_is_rejected(self):
        with self.assertRaises(ValueError):
            Example(prompt="   ", label="haiku", source="seed")

    def test_identical_prompts_share_a_group_so_they_cannot_straddle_a_split(self):
        a = Example(prompt="Read The File", label="haiku", source="mined")
        b = Example(prompt="read the file", label="sonnet", source="mined")
        self.assertEqual(a.group, b.group)


class SplitPolicyTest(unittest.TestCase):
    def test_synthetic_rows_never_reach_the_test_set(self):
        rows = [Example(f"seed prompt {i}", "haiku", "seed") for i in range(200)]
        parts = split(rows)
        self.assertEqual(len(parts["train"]), 200)
        self.assertEqual(parts["test"], [])
        self.assertEqual(parts["val"], [])

    def test_hand_labelled_rows_are_test_only(self):
        rows = [Example(f"golden prompt {i}", "opus", "golden") for i in range(50)]
        parts = split(rows)
        self.assertEqual(len(parts["test"]), 50)
        self.assertEqual(parts["train"], [])

    def test_real_rows_are_divided_roughly_as_asked(self):
        rows = [Example(f"mined prompt {i}", "sonnet", "mined") for i in range(2000)]
        parts = split(rows, val_frac=0.15, test_frac=0.15)
        self.assertAlmostEqual(len(parts["test"]) / 2000, 0.15, delta=0.03)
        self.assertAlmostEqual(len(parts["val"]) / 2000, 0.15, delta=0.03)

    def test_a_group_lands_entirely_on_one_side(self):
        rows = [
            Example(f"variant {n} of thing {i}", "sonnet", "mined", group=f"g{i}")
            for i in range(300) for n in range(4)
        ]
        parts = split(rows)
        where: dict[str, set[str]] = {}
        for name, subset in parts.items():
            for example in subset:
                where.setdefault(example.group, set()).add(name)
        straddling = {g for g, names in where.items() if len(names) > 1}
        self.assertEqual(straddling, set())

    def test_the_split_is_deterministic(self):
        rows = [Example(f"prompt {i}", "opus", "distilled") for i in range(500)]
        first = {k: [e.id for e in v] for k, v in split(rows).items()}
        second = {k: [e.id for e in v] for k, v in split(rows).items()}
        self.assertEqual(first, second)


class DedupeTest(unittest.TestCase):
    def test_a_human_label_outranks_a_model_label_for_the_same_prompt(self):
        rows = [
            Example("clean this up", "sonnet", "distilled", "claude-opus-5", weight=0.9),
            Example("clean this up", "opus", "golden", "human", weight=1.0),
        ]
        kept = dedupe(rows)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].label, "opus")

    def test_an_outcome_label_outranks_the_taxonomy(self):
        rows = [
            Example("run the tests", "haiku", "seed", "taxonomy", weight=1.0),
            Example("run the tests", "sonnet", "mined", "outcome", weight=0.5),
        ]
        self.assertEqual(dedupe(rows)[0].label, "sonnet")


class RoundTripTest(unittest.TestCase):
    def test_rows_survive_a_write_and_read(self):
        rows = [Example("read src/a.py", "haiku", "mined", "outcome",
                        signals={"phase": "tool_loop", "failures": 2})]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "d.jsonl"
            self.assertEqual(write(path, rows), 1)
            back = read(path)
        self.assertEqual(back[0].signals["failures"], 2)
        self.assertEqual(back[0].id, rows[0].id)


class GeneratorTest(unittest.TestCase):
    def test_the_seed_generator_is_reproducible(self):
        first = [e.prompt for e in seed_module.build(per_template=3, per_pair=2, seed=1)]
        second = [e.prompt for e in seed_module.build(per_template=3, per_pair=2, seed=1)]
        self.assertEqual(first, second)

    def test_seed_data_covers_every_tier(self):
        labels = {e.label for e in seed_module.build(per_template=2, per_pair=2)}
        self.assertEqual(labels, set(TIERS))

    def test_no_unfilled_slots_leak_into_prompts(self):
        for example in seed_module.build(per_template=2, per_pair=2):
            self.assertNotIn("{", example.prompt, example.prompt)

    def test_both_sides_of_a_minimal_pair_share_a_group(self):
        rows = [e for e in seed_module.build(per_template=1, per_pair=2)
                if e.group.startswith("contrast:")]
        by_group: dict[str, set[str]] = {}
        for example in rows:
            by_group.setdefault(example.group, set()).add(example.label)
        self.assertTrue(by_group)
        self.assertTrue(all(len(labels) == 2 for labels in by_group.values()))

    def test_the_golden_set_is_balanced_enough_to_be_informative(self):
        rows = golden.build()
        counts = {tier: sum(e.label == tier for e in rows) for tier in TIERS}
        self.assertTrue(all(count >= 15 for count in counts.values()), counts)
        self.assertTrue(all(e.label_source == "human" for e in rows))

    def test_golden_prompts_are_not_copied_from_the_taxonomy(self):
        seeded = {e.prompt.lower() for e in seed_module.build(per_template=8, per_pair=5)}
        overlap = {e.prompt.lower() for e in golden.build()} & seeded
        self.assertEqual(overlap, set())


if __name__ == "__main__":
    unittest.main()
