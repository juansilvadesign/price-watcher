import json
import tempfile
import unittest
from pathlib import Path

from pricewatch.registry import ConfigError, load_target, load_targets

VALID = {
    "id": "x", "label": "L", "adapter": "buyticketbrasil",
    "params": {"event_slug": "s", "data_millis": 1, "evento_local": "e"},
    "rules": {"below_threshold": {"enabled": True, "price_brl": 275.0}},
}


class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def write(self, name, cfg):
        p = self.dir / name
        p.write_text(json.dumps(cfg), encoding="utf-8")
        return p

    def test_valid_target_loads(self):
        t = load_target(self.write("x.json", VALID))
        self.assertEqual(t.id, "x")

    def test_brl_threshold_becomes_centavos(self):
        t = load_target(self.write("x.json", VALID))
        self.assertEqual(t.rules["below_threshold"]["price_cents"], 27500)
        self.assertNotIn("price_brl", t.rules["below_threshold"])

    def test_enabled_rule_without_its_parameter_is_fatal(self):
        """The whole point: a rule that can never fire must not load silently."""
        cfg = dict(VALID, rules={"below_threshold": {"enabled": True}})
        with self.assertRaises(ConfigError) as cm:
            load_target(self.write("x.json", cfg))
        self.assertIn("never fires", str(cm.exception))

    def test_disabled_rule_without_parameter_is_allowed(self):
        cfg = dict(VALID, rules={"below_threshold": {"enabled": False}})
        self.assertIsNotNone(load_target(self.write("x.json", cfg)))

    def test_bad_direction_value_is_fatal(self):
        """Presence is not enough -- a nonsense value must not load either."""
        cfg = dict(VALID, rules={"price_changed": {"enabled": True, "direction": "sideways"}})
        with self.assertRaises(ConfigError) as cm:
            load_target(self.write("x.json", cfg))
        self.assertIn("any/down/up", str(cm.exception))

    def test_min_delta_brl_becomes_centavos(self):
        cfg = dict(VALID, rules={"price_changed": {"enabled": True, "direction": "any",
                                                   "min_delta_brl": 2.50}})
        t = load_target(self.write("x.json", cfg))
        self.assertEqual(t.rules["price_changed"]["min_delta_cents"], 250)

    def test_unknown_rule_name_is_fatal(self):
        cfg = dict(VALID, rules={"typo_rule": {"enabled": True}})
        with self.assertRaises(ConfigError):
            load_target(self.write("x.json", cfg))

    def test_id_must_match_filename(self):
        with self.assertRaises(ConfigError):
            load_target(self.write("other.json", VALID))

    def test_missing_required_key_is_fatal(self):
        cfg = {k: v for k, v in VALID.items() if k != "params"}
        with self.assertRaises(ConfigError):
            load_target(self.write("x.json", cfg))

    def test_invalid_json_is_fatal(self):
        (self.dir / "x.json").write_text("{not json", encoding="utf-8")
        with self.assertRaises(ConfigError):
            load_target(self.dir / "x.json")

    def test_only_filter_rejects_an_unknown_id(self):
        self.write("x.json", VALID)
        with self.assertRaises(ConfigError):
            load_targets(self.dir, only=["nope"])


class TestRealTargets(unittest.TestCase):
    """All eight shipped targets must actually load.

    The count is pinned: a target file that fails to parse would otherwise just
    vanish from the registry, and a night silently stops being watched.

    Sector and entry_class are pinned PER TARGET rather than as one blanket value,
    because they now genuinely differ and the difference is load-bearing. Rock in Rio
    does not check the ticket type at the gate, so `entry_class` is null and the
    cheapest class wins; Maracanã DOES, so SOAD names the two classes Juan can actually
    present. A blanket assertion would have to be loosened to accommodate both, and a
    loosened one would no longer notice `null` appearing on the target where being
    turned away at the gate is the cost.
    """

    #: id -> (sector, entry_class). Verbatim; every shipped target must appear.
    EXPECTED_FILTERS = {
        **{f"rockinrio2026-09-{d}": (["Gramado"], None)
           for d in ("04", "05", "06", "07", "11", "12", "13")},
        "soad2027-01-15": (["Pista Premium Itaú Personalité"], ["Meia Estudante", "Inteira"]),
    }

    def test_shipped_targets_are_valid(self):
        root = Path(__file__).resolve().parent.parent / "targets"
        targets = load_targets(root)
        self.assertEqual(len(targets), 8)
        for t in targets:
            self.assertEqual(t.adapter, "buyticketbrasil")
            self.assertIn(t.id, self.EXPECTED_FILTERS, f"{t.id} is not pinned here")
            sector, entry_class = self.EXPECTED_FILTERS[t.id]
            self.assertEqual(t.filters["extra"]["sector"], sector, f"{t.id} sector")
            self.assertEqual(t.filters["extra"]["entry_class"], entry_class,
                             f"{t.id} entry_class -- the gate-verification call")
            # WHICH rules are armed is pinned in test_rules.TestSuccessiveNewLows;
            # here we only assert every rule is structurally valid and loadable.
            self.assertTrue(set(t.rules), f"{t.id} declares no rules")
            self.assertTrue(t.rules["below_threshold"]["price_cents"] > 0,
                            "a disabled rule must keep its parameter for re-arming")
        # Without this the pin goes vacuous the moment a target is renamed.
        self.assertEqual(set(self.EXPECTED_FILTERS) - {t.id for t in targets}, set(),
                         "a pinned target is missing from targets/")


class TestWindowRuleValidation(unittest.TestCase):
    """`lowest_in_window` joins the "enabled without its parameter must refuse to
    load" contract. A window rule that silently defaults would look armed and never
    fire -- the same failure shape the registry exists to prevent."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def load(self, rule_cfg):
        cfg = dict(VALID, id="x", rules={"lowest_in_window": rule_cfg})
        p = self.dir / "x.json"
        p.write_text(json.dumps(cfg), encoding="utf-8")
        return load_target(p)

    def test_enabled_without_window_hours_refuses_to_load(self):
        with self.assertRaises(ConfigError):
            self.load({"enabled": True})

    def test_zero_and_negative_windows_refuse_to_load(self):
        for bad in (0, -1, -0.5):
            with self.subTest(bad=bad), self.assertRaises(ConfigError):
                self.load({"enabled": True, "window_hours": bad})

    def test_a_boolean_window_refuses_to_load(self):
        """`isinstance(True, int)` is True in Python, so a bare `true` would otherwise
        load as a plausible-looking 1-hour window nobody wrote."""
        with self.assertRaises(ConfigError):
            self.load({"enabled": True, "window_hours": True})

    def test_a_string_window_refuses_to_load(self):
        with self.assertRaises(ConfigError):
            self.load({"enabled": True, "window_hours": "6"})

    def test_a_valid_window_loads(self):
        """Control leg: the refusals above must not be a rule that never loads."""
        t = self.load({"enabled": True, "window_hours": 6})
        self.assertEqual(t.rules["lowest_in_window"]["window_hours"], 6)

    def test_a_disabled_rule_is_not_validated(self):
        """Consistent with the other rules: disabled config is inert, not checked."""
        t = self.load({"enabled": False})
        self.assertFalse(t.rules["lowest_in_window"]["enabled"])


if __name__ == "__main__":
    unittest.main()


class TestCriticalPriceConfig(unittest.TestCase):
    """`critical_price` goes through the same BRL door as `below_threshold`."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def write(self, cfg):
        base = dict(VALID)
        base["rules"] = {"critical_price": cfg}
        p = self.dir / "x.json"
        p.write_text(json.dumps(base), encoding="utf-8")
        return p

    def test_brl_floor_becomes_centavos(self):
        t = load_target(self.write({"enabled": True, "price_brl": 200.0}))
        self.assertEqual(t.rules["critical_price"]["price_cents"], 20000)
        self.assertNotIn("price_brl", t.rules["critical_price"])

    def test_enabled_without_a_price_refuses_to_load(self):
        with self.assertRaises(ConfigError):
            load_target(self.write({"enabled": True}))

    def test_a_bare_true_is_rejected_not_read_as_one_real(self):
        """`isinstance(True, int)` is True, so `price_brl: true` would otherwise
        convert to R$ 1,00 — a floor that reads as armed and matches nothing. It has
        to be caught before conversion; afterwards it is an ordinary 100."""
        with self.assertRaises(ConfigError):
            load_target(self.write({"enabled": True, "price_brl": True}))

    def test_zero_and_negative_floors_are_rejected(self):
        for bad in (0, -5):
            with self.subTest(price_brl=bad), self.assertRaises(ConfigError):
                load_target(self.write({"enabled": True, "price_brl": bad}))

    def test_a_disabled_floor_still_converts_but_never_validates(self):
        """Mirrors below_threshold: a disabled rule keeps its value for later."""
        t = load_target(self.write({"enabled": False, "price_brl": 200.0}))
        self.assertEqual(t.rules["critical_price"]["price_cents"], 20000)
