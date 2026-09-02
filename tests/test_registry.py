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
    """All seven shipped targets must actually load.

    The count is pinned: a target file that fails to parse would otherwise just
    vanish from the registry, and a night silently stops being watched.
    """

    def test_shipped_targets_are_valid(self):
        root = Path(__file__).resolve().parent.parent / "targets"
        targets = load_targets(root)
        self.assertEqual(len(targets), 7)
        for t in targets:
            self.assertEqual(t.adapter, "buyticketbrasil")
            self.assertEqual(t.filters["extra"]["sector"], ["Gramado"])
            # WHICH rules are armed is pinned in test_rules.TestSuccessiveNewLows;
            # here we only assert every rule is structurally valid and loadable.
            self.assertTrue(set(t.rules), f"{t.id} declares no rules")
            self.assertTrue(t.rules["below_threshold"]["price_cents"] > 0,
                            "a disabled rule must keep its parameter for re-arming")


if __name__ == "__main__":
    unittest.main()
