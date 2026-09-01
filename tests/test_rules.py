import tempfile
import unittest
from pathlib import Path

from pricewatch import rules
from pricewatch.history import History
from pricewatch.models import Reading
from tests.helpers import make_target


def reading(cents, ts="2026-09-01T00:00:00+00:00", qty=10, item="Gramado || Inteira"):
    return Reading(target_id="t1", site="s", item=item, price_cents=cents,
                   currency="BRL", quantity=qty, captured_at=ts, source_url="u")


class RuleCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.history = History(Path(self.tmp.name))
        self.addCleanup(self.tmp.cleanup)

    def seed(self, *runs):
        """Each arg is one run: a tuple of prices sharing a captured_at."""
        for i, prices in enumerate(runs):
            ts = f"2026-08-{20+i:02d}T00:00:00+00:00"
            self.history.append("t1", [reading(p, ts) for p in prices])


class TestLowestEver(RuleCase):
    def test_fires_when_it_beats_the_record(self):
        self.seed((30000,), (29000,))
        t = make_target(rules={"lowest_ever": {"enabled": True}})
        self.assertIsNotNone(rules.lowest_ever(t, [reading(28000)], self.history))

    def test_silent_when_equal_to_the_record(self):
        self.seed((29000,))
        t = make_target(rules={"lowest_ever": {"enabled": True}})
        self.assertIsNone(rules.lowest_ever(t, [reading(29000)], self.history))

    def test_silent_on_the_very_first_run(self):
        """No history means every price is trivially a record -- that is not news."""
        t = make_target(rules={"lowest_ever": {"enabled": True}})
        self.assertIsNone(rules.lowest_ever(t, [reading(1)], self.history))


class TestBelowThreshold(RuleCase):
    def rule_target(self):
        return make_target(rules={"below_threshold": {"enabled": True, "price_cents": 27500}})

    def test_fires_on_crossing_down(self):
        self.seed((28600,))
        self.assertIsNotNone(rules.below_threshold(self.rule_target(), [reading(27000)], self.history))

    def test_fires_at_exactly_the_ceiling(self):
        self.seed((28600,))
        self.assertIsNotNone(rules.below_threshold(self.rule_target(), [reading(27500)], self.history))

    def test_silent_when_still_above(self):
        self.seed((28600,))
        self.assertIsNone(rules.below_threshold(self.rule_target(), [reading(28000)], self.history))

    def test_does_not_repeat_while_already_below(self):
        """Edge-triggered: re-alerting every cron tick trains you to ignore it."""
        self.seed((27000,))
        self.assertIsNone(rules.below_threshold(self.rule_target(), [reading(26900)], self.history))


class TestDropPct(RuleCase):
    def rule_target(self):
        return make_target(rules={"drop_pct": {"enabled": True, "pct": 5.0}})

    def test_fires_at_or_above_the_threshold(self):
        self.seed((30000,))
        self.assertIsNotNone(rules.drop_pct(self.rule_target(), [reading(28500)], self.history))  # -5.0%

    def test_silent_below_the_threshold(self):
        self.seed((30000,))
        self.assertIsNone(rules.drop_pct(self.rule_target(), [reading(28800)], self.history))  # -4.0%

    def test_silent_on_a_rise(self):
        self.seed((30000,))
        self.assertIsNone(rules.drop_pct(self.rule_target(), [reading(31000)], self.history))

    def test_silent_without_a_previous_run(self):
        self.assertIsNone(rules.drop_pct(self.rule_target(), [reading(100)], self.history))


class TestPriceChanged(RuleCase):
    def target(self, direction="any", **extra):
        cfg = {"enabled": True, "direction": direction}
        cfg.update(extra)
        return make_target(rules={"price_changed": cfg})

    def test_fires_on_any_move_down(self):
        self.seed((30000,))
        self.assertIsNotNone(rules.price_changed(self.target(), [reading(29999)], self.history))

    def test_fires_on_any_move_up(self):
        self.seed((30000,))
        a = rules.price_changed(self.target(), [reading(30001)], self.history)
        self.assertIsNotNone(a)
        self.assertIn("UP", a.headline)

    def test_silent_when_the_price_held(self):
        self.seed((30000,))
        self.assertIsNone(rules.price_changed(self.target(), [reading(30000)], self.history))

    def test_direction_down_ignores_a_rise(self):
        self.seed((30000,))
        self.assertIsNone(rules.price_changed(self.target("down"), [reading(31000)], self.history))
        self.assertIsNotNone(rules.price_changed(self.target("down"), [reading(29000)], self.history))

    def test_direction_up_ignores_a_fall(self):
        self.seed((30000,))
        self.assertIsNone(rules.price_changed(self.target("up"), [reading(29000)], self.history))

    def test_min_delta_filters_churn(self):
        self.seed((30000,))
        t = self.target(min_delta_cents=500)
        self.assertIsNone(rules.price_changed(t, [reading(29800)], self.history))   # -2,00
        self.assertIsNotNone(rules.price_changed(t, [reading(29400)], self.history))  # -6,00

    def test_silent_without_a_previous_run(self):
        self.assertIsNone(rules.price_changed(self.target(), [reading(100)], self.history))


class TestEvaluate(RuleCase):
    def test_disabled_rules_never_run(self):
        self.seed((30000,))
        t = make_target(rules={
            "lowest_ever": {"enabled": False},
            "drop_pct": {"enabled": False, "pct": 1.0},
        })
        self.assertEqual(rules.evaluate(t, [reading(1000)], self.history), [])

    def test_several_rules_can_fire_together(self):
        self.seed((30000,))
        t = make_target(rules={
            "lowest_ever": {"enabled": True},
            "below_threshold": {"enabled": True, "price_cents": 27500},
            "drop_pct": {"enabled": True, "pct": 5.0},
        })
        fired = {a.rule for a in rules.evaluate(t, [reading(20000)], self.history)}
        self.assertEqual(fired, {"lowest_ever", "below_threshold", "drop_pct"})

    def test_history_uses_the_cheapest_of_the_last_run_not_the_last_line(self):
        """A run writes many rows; the baseline must be that run's minimum."""
        self.seed((30000, 28000, 35000))
        self.assertEqual(self.history.last_run_min_cents("t1"), 28000)


if __name__ == "__main__":
    unittest.main()
