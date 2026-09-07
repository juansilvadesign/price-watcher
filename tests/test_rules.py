import datetime as _dt
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


class TestSuccessiveNewLows(RuleCase):
    """Juan's stated requirement, 2026-09-01, encoded verbatim.

    "if the price is R$250 now and the lowest is R$230, it will notify me if 17:00
    the price drops to R$228 and also if 17:01 the price drops to R$220"

    The second drop must fire too — there is no cooldown and no suppression. Each new
    low moves the record down, so the next low is measured against it.
    """

    def test_each_successive_new_low_fires(self):
        t = make_target(rules={"lowest_ever": {"enabled": True}})
        self.seed((25000,), (23000,))                       # now 250,00; record 230,00
        self.assertEqual(self.history.min_price_cents("t1"), 23000)

        # 17:00 -> 228,00 beats the 230,00 record
        first = rules.evaluate(t, [reading(22800)], self.history)
        self.assertEqual([a.rule for a in first], ["lowest_ever"])
        self.history.append("t1", [reading(22800, "2026-09-01T20:00:00+00:00")])

        # 17:01 -> 220,00 beats the new 228,00 record, one minute later
        second = rules.evaluate(t, [reading(22000)], self.history)
        self.assertEqual([a.rule for a in second], ["lowest_ever"])
        self.assertIn("R$ 220,00", second[0].headline)

    def test_a_drop_that_is_not_a_new_low_stays_silent(self):
        """400 -> 370 is a big move but not a record. Explicitly NOT wanted."""
        t = make_target(rules={"lowest_ever": {"enabled": True}})
        self.seed((23000,), (40000,))
        self.assertEqual(rules.evaluate(t, [reading(37000)], self.history), [])

    #: id -> the rules that must be armed. Verbatim per target, not a rule with
    #: exceptions: the SOAD entry is a deliberate THIRD shape and a branch that tried
    #: to express all three would stop being readable as intent.
    EXPECTED_ARMED = {
        # Rock in Rio buy nights.
        **{f"rockinrio2026-09-{d}": ["critical_price", "lowest_ever", "lowest_in_window"]
           for d in ("04", "05", "11")},
        # Rock in Rio tracking nights.
        **{f"rockinrio2026-09-{d}": ["critical_price", "lowest_ever"]
           for d in ("06", "07", "12", "13")},
        # SOAD: critical_price ALONE. Juan goes only if a ticket can be had under
        # R$400, so "this is a new low" at R$1.100,00 is noise on the way to a number
        # that has not been reached.
        "soad2027-01-15": ["critical_price"],
    }

    def test_the_shipped_targets_arm_exactly_the_intended_rules(self):
        """Pinned per target rather than as a blanket rule.

        `lowest_in_window` is armed ONLY on the nights Juan would actually buy; on a
        tracking night it would only add alerts he cannot act on. Everything else stays
        off — that was an explicit call, not an oversight.

        `critical_price` is armed on ALL of them, but for two DIFFERENT reasons, and
        the difference is why this is a map and not a branch:

          * On the Rock in Rio nights it is a data-quality guard as much as an alert —
            those nights run `lowest_ever`, which one mispriced row kills permanently.
          * On SOAD it is the ONLY armed rule, so it is purely an alert. Its anomaly
            floor has no baseline left to protect, which is precisely what makes a
            R$ 400,00 floor coherent ~3x under a R$ 1.197,90 market. ⛔ If `lowest_ever`
            is ever re-armed there, that number has to be revisited the same day — this
            test failing is the intended way to find that out.
        """
        from pathlib import Path
        from pricewatch.registry import load_targets
        seen = set()
        for t in load_targets(Path(__file__).resolve().parent.parent / "targets"):
            armed = sorted(n for n, c in t.rules.items() if c.get("enabled"))
            self.assertIn(t.id, self.EXPECTED_ARMED, f"{t.id} is not pinned here")
            self.assertEqual(armed, self.EXPECTED_ARMED[t.id], f"{t.id} has {armed} armed")
            seen.add(t.id)
        # Without this the map goes vacuous the moment an id is renamed, and the pin
        # would keep passing while guarding nothing.
        self.assertEqual(set(self.EXPECTED_ARMED) - seen, set(),
                         "a pinned target is missing from targets/")


class TestChangeOnlyRecording(RuleCase):
    def test_an_identical_run_is_not_recorded(self):
        rs = [reading(25000, item="A"), reading(26000, item="B")]
        self.assertTrue(self.history.append_if_changed("t1", rs))
        before = len(self.history.load("t1"))
        self.assertFalse(self.history.append_if_changed("t1", rs))
        self.assertEqual(len(self.history.load("t1")), before)

    def test_a_price_move_is_recorded(self):
        self.history.append_if_changed("t1", [reading(25000, item="A")])
        self.assertTrue(self.history.append_if_changed("t1", [reading(24900, item="A")]))

    def test_a_quantity_move_alone_is_recorded(self):
        """Stock moving is real signal even when the price held."""
        self.history.append_if_changed("t1", [reading(25000, item="A", qty=10)])
        self.assertTrue(self.history.append_if_changed("t1", [reading(25000, item="A", qty=3)]))

    def test_an_item_appearing_or_vanishing_is_recorded(self):
        self.history.append_if_changed("t1", [reading(25000, item="A")])
        self.assertTrue(self.history.append_if_changed(
            "t1", [reading(25000, item="A"), reading(30000, item="B")]))

    def test_dedup_does_not_hide_a_record_low_from_lowest_ever(self):
        """The dedup must never cost an alert."""
        t = make_target(rules={"lowest_ever": {"enabled": True}})
        self.history.append_if_changed("t1", [reading(25000)])
        for _ in range(5):                                  # many unchanged polls
            self.history.append_if_changed("t1", [reading(25000)])
        self.assertEqual(len(self.history.load("t1")), 1)
        self.assertEqual([a.rule for a in rules.evaluate(t, [reading(24000)], self.history)],
                         ["lowest_ever"])

    def test_an_empty_run_is_never_treated_as_unchanged(self):
        """Sold out is data, but it must not silently look like 'nothing happened'."""
        self.assertFalse(self.history.append_if_changed("t1", []))


class TestLowestInWindow(RuleCase):
    """A rolling-window low -- and the change-log trap sitting underneath it.

    `lowest_ever` ratchets shut: every record it sets raises its own bar, so it is
    quietest exactly when you most need it (the day you buy). This rule's baseline
    expires instead, so it cannot ratchet.
    """

    def seed_at(self, *runs):
        """Each arg is (hours_ago, price_cents) -- one recorded run, one price."""
        for hours_ago, price in runs:
            ts = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=hours_ago)
                  ).replace(microsecond=0).isoformat()
            self.history.append("t1", [reading(price, ts)])

    def target(self, hours=6):
        return make_target(rules={"lowest_in_window":
                                  {"enabled": True, "window_hours": hours}})

    # --- ordinary behaviour ----------------------------------------------------
    def test_fires_when_it_beats_the_window(self):
        self.seed_at((3, 30000), (1, 29000))
        self.assertIsNotNone(rules.lowest_in_window(self.target(), [reading(28000)], self.history))

    def test_silent_when_equal_to_the_window_low(self):
        self.seed_at((1, 29000))
        self.assertIsNone(rules.lowest_in_window(self.target(), [reading(29000)], self.history))

    def test_silent_on_the_very_first_run(self):
        self.assertIsNone(rules.lowest_in_window(self.target(), [reading(1)], self.history))

    # --- the change log's carry-forward ----------------------------------------
    def test_a_window_with_no_rows_reads_the_standing_price_not_no_data(self):
        """`append_if_changed` means an empty window is usually "nothing moved", not
        "nothing known". Without the carry-forward the baseline is None and the rule
        goes silent on a real dip."""
        self.seed_at((30, 30000))          # far outside a 6h window, still standing
        self.assertIsNotNone(rules.lowest_in_window(self.target(), [reading(28000)], self.history))

    def test_known_bad_leg_returning_to_a_price_already_held_in_the_window(self):
        """Without the carry-forward this fires -- falsely, and repeatedly.

        The price stood at 250 when the window opened, rose to 300, and has now come
        back to 250. That is a return, not a new low; a market oscillating inside the
        window would re-alert on every swing back, which is level-triggering in
        disguise. A naive `min` over rows *inside* the window sees only 300 and fires.
        """
        self.seed_at((10, 25000), (5, 30000))
        self.assertIsNone(rules.lowest_in_window(self.target(), [reading(25000)], self.history))

    def test_control_a_genuine_new_low_in_that_same_shape_still_fires(self):
        """Pairs with the leg above: the carry-forward must not simply mute the rule."""
        self.seed_at((10, 25000), (5, 30000))
        self.assertIsNotNone(rules.lowest_in_window(self.target(), [reading(24000)], self.history))

    # --- why the rule exists ---------------------------------------------------
    def test_it_speaks_where_lowest_ever_has_ratcheted_shut(self):
        """Juan's 05/09 shape on 2026-09-01: an all-time record set days ago, the
        market trading far above it since, and a real dip today. `lowest_ever` cannot
        see the dip; the window can."""
        self.seed_at((72, 25000), (70, 34000))
        t = make_target(rules={"lowest_ever": {"enabled": True},
                               "lowest_in_window": {"enabled": True, "window_hours": 6}})
        now = [reading(30000)]
        self.assertIsNone(rules.lowest_ever(t, now, self.history),
                          "lowest_ever should be silent -- 300 is nowhere near the 250 record")
        self.assertIsNotNone(rules.lowest_in_window(t, now, self.history),
                             "the window should still see 340 -> 300 as today's low")


if __name__ == "__main__":
    unittest.main()


class TestCriticalPrice(RuleCase):
    """The anomaly band: alert immediately, and never let it become a baseline.

    Cadence is "once on entering the band, then again on each new low inside it".
    Not level-triggered (a stuck mispricing would alert once a minute forever) and
    not once-only (a market genuinely falling through the floor should be reported
    the whole way down).
    """

    FLOOR = 20000  # R$ 200,00 -- the value armed on the three buy nights

    def target(self, floor=None, **extra):
        cfg = {"critical_price": {"enabled": True,
                                  "price_cents": self.FLOOR if floor is None else floor}}
        cfg.update(extra)
        return make_target(rules=cfg)

    # --- cadence ---------------------------------------------------------------
    def test_fires_on_entering_the_band(self):
        self.seed((27500,), (22000,))
        self.assertIsNotNone(rules.critical_price(self.target(), [reading(6600)], self.history))

    def test_fires_again_on_a_new_low_inside_the_band(self):
        self.seed((22000,), (18000,))
        self.assertIsNotNone(rules.critical_price(self.target(), [reading(17500)], self.history))

    def test_silent_while_a_sub_floor_price_merely_holds(self):
        self.seed((27500,), (18000,))
        self.assertIsNone(rules.critical_price(self.target(), [reading(18000)], self.history))

    def test_silent_on_a_rise_that_stays_inside_the_band(self):
        self.seed((27500,), (17000,))
        self.assertIsNone(rules.critical_price(self.target(), [reading(17800)], self.history))

    def test_silent_above_the_floor(self):
        self.seed((27500,))
        self.assertIsNone(rules.critical_price(self.target(), [reading(22000)], self.history))

    def test_exactly_at_the_floor_is_not_below_it(self):
        self.seed((27500,))
        self.assertIsNone(rules.critical_price(self.target(), [reading(self.FLOOR)], self.history))

    def test_fires_on_the_very_first_run(self):
        """Deliberately unlike `lowest_ever`, which is silent on run one.

        That silence exists because with no history every price is trivially a record.
        Nothing vacuous happens here: the floor is an absolute number a human wrote
        down, so the first reading to cross it has crossed it.
        """
        self.assertIsNotNone(rules.critical_price(self.target(), [reading(6600)], self.history))

    def test_it_re_arms_after_the_price_leaves_the_band(self):
        self.seed((27500,), (18000,), (26000,))
        self.assertIsNotNone(rules.critical_price(self.target(), [reading(19000)], self.history))


class TestAnomalyFloorExclusion(RuleCase):
    """A sub-floor reading must never become a baseline.

    This is the half that bites. `lowest_ever` has no expiry, so ONE bad row kills it
    for good -- which is not hypothetical: see the verbatim 04/09 leg below.
    """

    FLOOR = 20000

    def armed(self, **extra):
        cfg = {"critical_price": {"enabled": True, "price_cents": self.FLOOR},
               "lowest_ever": {"enabled": True}}
        cfg.update(extra)
        return make_target(rules=cfg)

    def unarmed(self):
        return make_target(rules={"lowest_ever": {"enabled": True}})

    def seed_at(self, *runs):
        for hours_ago, price in runs:
            ts = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=hours_ago)
                  ).replace(microsecond=0).isoformat()
            self.history.append("t1", [reading(price, ts)])

    # --- known-bad leg: the real 04/09 poisoning -------------------------------
    def test_known_bad_leg_one_glitched_row_kills_lowest_ever_for_good(self):
        """Production, 2026-09-02: R$ 220,00 -> R$ 66,00 (one run) -> R$ 275,00.

        With no floor the R$ 66,00 is the all-time record, and because `lowest_ever`
        never expires, a genuine R$ 210,00 two days later -- a real new low against a
        R$ 220,00 market -- says nothing at all. This leg FAILS on the fixed source
        only if the exclusion is removed; it is here to pin that, not to pass quietly.
        """
        self.seed((22000,), (6600,), (27500,))
        self.assertIsNone(
            rules.lowest_ever(self.unarmed(), [reading(21000)], self.history),
            "unarmed: R$ 66,00 holds the record, so a real R$ 210,00 is silent")

    def test_the_floor_restores_it(self):
        """Same history, same reading, floor armed. Pairs with the leg above so the
        exclusion cannot simply be muting the rule."""
        self.seed((22000,), (6600,), (27500,))
        self.assertIsNotNone(rules.lowest_ever(self.armed(), [reading(21000)], self.history))

    def test_the_exclusion_heals_retroactively(self):
        """Applied on read, so a history already carrying the bad row recovers the
        moment the floor is configured -- no rewrite of the JSONL, no data loss."""
        self.seed((22000,), (6600,))
        self.assertEqual(self.history.min_price_cents("t1"), 6600)
        self.assertEqual(self.history.min_price_cents("t1", floor_cents=self.FLOOR), 22000)

    # --- the readings are filtered, not just the baseline ----------------------
    def test_an_anomaly_does_not_hide_a_real_new_low_in_the_same_run(self):
        """A glitched `Inteira` and a genuine `Meia Estudante` in one run.

        Taking the cheapest first and rejecting it when sub-floor would mute the whole
        run, hiding the real low for as long as the glitch lasted.
        """
        self.seed((22000,))
        run = [reading(6600, item="Gramado || Inteira"),
               reading(21000, item="Gramado || Meia Estudante")]
        alert = rules.lowest_ever(self.armed(), run, self.history)
        self.assertIsNotNone(alert)
        self.assertEqual(alert.reading.price_cents, 21000)
        self.assertEqual(alert.reading.item, "Gramado || Meia Estudante")

    def test_silent_when_every_reading_in_the_run_is_sub_floor(self):
        self.seed((22000,))
        run = [reading(6600), reading(7000)]
        self.assertIsNone(rules.lowest_ever(self.armed(), run, self.history))

    # --- the band belongs to critical_price ------------------------------------
    def test_relative_rules_stay_silent_inside_the_band(self):
        """Without this the exclusion alone would level-trigger `lowest_in_window`.

        Sub-floor rows never enter the baseline, so the baseline stays at the last
        legitimate price and EVERY sub-floor run satisfies `now < prior` -- an alert
        every minute for as long as the mispricing stands. Handing the band to
        `critical_price` is what keeps the chosen cadence honest.
        """
        self.seed_at((3, 27500))
        t = make_target(rules={"critical_price": {"enabled": True, "price_cents": self.FLOOR},
                               "lowest_in_window": {"enabled": True, "window_hours": 6}})
        self.assertIsNone(rules.lowest_in_window(t, [reading(6600)], self.history))

    def test_control_the_same_shape_just_above_the_floor_still_fires(self):
        """Pairs with the leg above: the band is silenced, not the rule."""
        self.seed_at((3, 27500))
        t = make_target(rules={"critical_price": {"enabled": True, "price_cents": self.FLOOR},
                               "lowest_in_window": {"enabled": True, "window_hours": 6}})
        self.assertIsNotNone(rules.lowest_in_window(t, [reading(20500)], self.history))

    def test_window_baseline_ignores_a_sub_floor_row(self):
        self.seed_at((3, 27500), (2, 6600))
        t = make_target(rules={"critical_price": {"enabled": True, "price_cents": self.FLOOR},
                               "lowest_in_window": {"enabled": True, "window_hours": 6}})
        self.assertIsNotNone(rules.lowest_in_window(t, [reading(26000)], self.history),
                             "the R$ 66,00 must not have become the window's low")

    def test_carry_forward_skips_a_sub_floor_row_for_the_standing_price(self):
        """The row carried into an empty window must be the last LEGITIMATE one."""
        self.seed_at((30, 27500), (29, 6600))
        self.assertEqual(
            self.history.min_price_cents_since(
                "t1", _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=6),
                floor_cents=self.FLOOR),
            27500)

    # --- one switch ------------------------------------------------------------
    def test_disabling_critical_price_disables_the_protection_with_it(self):
        """One switch on purpose: a target must not alert on anomalies while still
        baselining them, nor the reverse."""
        self.seed((22000,), (6600,))
        t = make_target(rules={"critical_price": {"enabled": False, "price_cents": self.FLOOR},
                               "lowest_ever": {"enabled": True}})
        self.assertIsNone(rules._anomaly_floor(t))
        self.assertIsNone(rules.lowest_ever(t, [reading(21000)], self.history))


class TestCriticalPriceEndToEnd(RuleCase):
    """`evaluate()` over the real 04/09 sequence, one run at a time."""

    def test_the_04_09_sequence_alerts_once_and_keeps_the_baseline(self):
        t = make_target(rules={"critical_price": {"enabled": True, "price_cents": 20000},
                               "lowest_ever": {"enabled": True}})
        self.seed((27500,), (22000,))          # market at R$ 275,00 then R$ 220,00

        fired = rules.evaluate(t, [reading(6600)], self.history)
        self.assertEqual([a.rule for a in fired], ["critical_price"],
                         "the glitch alerts, and ONLY through the absolute rule")
        self.history.append("t1", [reading(6600, ts="2026-08-25T00:00:00+00:00")])

        # next minute: back to R$ 275,00, nothing to say
        self.assertEqual(rules.evaluate(t, [reading(27500)], self.history), [])

        # and the baseline survived -- a genuine R$ 210,00 still speaks
        self.assertEqual([a.rule for a in rules.evaluate(t, [reading(21000)], self.history)],
                         ["lowest_ever"])


class TestShippedTargetsArmTheFloor(unittest.TestCase):
    def test_every_shipped_target_arms_critical_price(self):
        """An unarmed target is one bad row away from a permanently dead `lowest_ever`,
        so the floor is not optional on a live watch."""
        from pricewatch.registry import load_targets
        root = Path(__file__).resolve().parent.parent / "targets"
        targets = load_targets(root)
        self.assertTrue(targets)
        for t in targets:
            with self.subTest(target=t.id):
                cfg = t.rules.get("critical_price")
                self.assertIsNotNone(cfg, f"{t.id} has no critical_price")
                self.assertTrue(cfg.get("enabled"), f"{t.id}: critical_price is disabled")
                self.assertIsInstance(cfg.get("price_cents"), int)
                self.assertGreater(cfg["price_cents"], 0)
