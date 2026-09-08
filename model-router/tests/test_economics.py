"""Cache economics: what a model switch actually costs once the prefix is warm."""

from __future__ import annotations

import math
import unittest

from ccrouter import config, economics
from ccrouter.config import HAIKU, OPUS, SONNET

CFG = config.load()


class CacheModelTest(unittest.TestCase):
    def test_the_ttl_picks_the_documented_write_multiplier(self):
        self.assertEqual(economics.CacheModel.for_ttl("5m").write_multiplier, 1.25)
        self.assertEqual(economics.CacheModel.for_ttl("1h").write_multiplier, 2.00)

    def test_reads_are_a_tenth_of_base_input(self):
        self.assertAlmostEqual(economics.CacheModel().read_multiplier, 0.10)


class SwitchTest(unittest.TestCase):
    def test_a_downgrade_gets_more_expensive_as_context_grows(self):
        small = economics.analyse_switch(CFG, SONNET, HAIKU, 5_000, horizon=6)
        large = economics.analyse_switch(CFG, SONNET, HAIKU, 200_000, horizon=6)
        self.assertLess(small.breakeven_requests, large.breakeven_requests)
        self.assertLess(large.rewarm_cost * 0.5, large.rewarm_cost)

    def test_sonnet_to_haiku_needs_a_long_turn_to_pay_off(self):
        analysis = economics.analyse_switch(CFG, SONNET, HAIKU, 50_000, horizon=6)
        self.assertGreater(analysis.breakeven_requests, 6)
        self.assertFalse(analysis.worth_it)

    def test_opus_to_haiku_pays_off_quickly_at_the_same_context(self):
        analysis = economics.analyse_switch(CFG, OPUS, HAIKU, 50_000, horizon=6)
        self.assertLess(analysis.breakeven_requests, 6)
        self.assertTrue(analysis.worth_it)

    def test_a_longer_horizon_can_rescue_a_marginal_switch(self):
        short = economics.analyse_switch(CFG, OPUS, SONNET, 50_000, horizon=4)
        long = economics.analyse_switch(CFG, OPUS, SONNET, 50_000, horizon=40)
        self.assertFalse(short.worth_it)
        self.assertTrue(long.worth_it)
        self.assertEqual(short.breakeven_requests, long.breakeven_requests)

    def test_an_upgrade_never_pays_for_itself_on_cost(self):
        analysis = economics.analyse_switch(CFG, HAIKU, OPUS, 50_000, horizon=6)
        self.assertEqual(analysis.breakeven_requests, math.inf)
        self.assertFalse(analysis.worth_it)
        self.assertGreater(analysis.rewarm_cost, 0)

    def test_a_switch_at_zero_context_is_free(self):
        analysis = economics.analyse_switch(CFG, OPUS, HAIKU, 0, horizon=6)
        self.assertEqual(analysis.rewarm_cost, 0.0)

    def test_the_one_hour_ttl_roughly_doubles_the_re_warm(self):
        five = economics.analyse_switch(
            CFG, OPUS, HAIKU, 50_000, horizon=6,
            cache=economics.CacheModel.for_ttl("5m"))
        hour = economics.analyse_switch(
            CFG, OPUS, HAIKU, 50_000, horizon=6,
            cache=economics.CacheModel.for_ttl("1h"))
        self.assertAlmostEqual(hour.rewarm_cost / five.rewarm_cost, 2.0 / 1.25, places=6)


class ExcursionTest(unittest.TestCase):
    def test_returning_costs_only_what_was_appended_while_away(self):
        analysis = economics.analyse_excursion(CFG, OPUS, HAIKU, 150_000, steps=3,
                                               appended_tokens=2_000)
        full_switch = economics.analyse_switch(CFG, HAIKU, OPUS, 150_000, horizon=1)
        # Rejoining is far cheaper than a cold re-warm of the same prefix.
        self.assertLess(analysis.rewarm_cost, full_switch.rewarm_cost)

    def test_a_long_excursion_forfeits_the_cheap_return(self):
        short = economics.analyse_excursion(CFG, OPUS, HAIKU, 150_000, steps=3)
        long = economics.analyse_excursion(CFG, OPUS, HAIKU, 150_000, steps=30)
        self.assertIn("lookback", long.detail)
        self.assertGreater(long.rewarm_cost, short.rewarm_cost)


class BestOptionTest(unittest.TestCase):
    def test_staying_wins_when_nothing_would_change(self):
        best = economics.best_option(CFG, SONNET, SONNET, 50_000, horizon=6)
        self.assertEqual(best.option, "stay")

    def test_staying_wins_over_an_unprofitable_downgrade(self):
        best = economics.best_option(CFG, SONNET, HAIKU, 50_000, horizon=6)
        self.assertEqual(best.option, "stay")

    def test_switching_wins_when_it_clearly_pays(self):
        best = economics.best_option(CFG, OPUS, HAIKU, 50_000, horizon=20)
        self.assertEqual(best.option, "switch")


class TurnLengthTest(unittest.TestCase):
    def test_the_prior_is_used_until_there_is_enough_data(self):
        model = economics.TurnLength(prior_mean=7.0)
        for _ in range(5):
            model.observe(2)
        self.assertEqual(model.expected_remaining(0), 7.0)

    def test_observed_turns_replace_the_prior(self):
        model = economics.TurnLength(prior_mean=20.0)
        for _ in range(100):
            model.observe(4)
        self.assertAlmostEqual(model.expected_remaining(0), 4.0, places=6)

    def test_remaining_shrinks_as_the_turn_goes_on(self):
        model = economics.TurnLength()
        for length in list(range(1, 13)) * 10:
            model.observe(length)
        self.assertGreater(model.expected_remaining(0), model.expected_remaining(8))

    def test_it_never_promises_zero_remaining_requests(self):
        model = economics.TurnLength()
        for _ in range(50):
            model.observe(3)
        self.assertGreaterEqual(model.expected_remaining(99), 1.0)

    def test_samples_are_bounded(self):
        model = economics.TurnLength()
        for _ in range(9000):
            model.observe(5)
        self.assertLessEqual(model.samples, 4096)


if __name__ == "__main__":
    unittest.main()
