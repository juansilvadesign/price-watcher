"""Per-target failure isolation in `watch.py`.

Until 2026-09-01 `main()` wrapped the entire target loop in one `except FilterError`,
so a config error on any target returned 2 immediately and every target after it was
never polled. `load_targets` sorts alphabetically, so *which* targets got dropped was
an accident of filename -- on the `*/5` cron line, 06/09 sorts first and would have
taken 07, 12 and 13 with it.

These tests drive `main()` against a stub adapter: no network, no fixture.
"""

import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

import watch
from pricewatch import adapters
from pricewatch.models import Reading


class _StubAdapter:
    """Canned readings per target id. `ROWS` is set by each test."""

    site = "stub"
    ROWS: dict = {}

    def fetch(self, target):
        return list(self.ROWS.get(target.id, []))


def _reading(target_id, sector="Gramado", cents=28600):
    return Reading(target_id=target_id, site="stub", item=f"{sector} || Inteira",
                   price_cents=cents, currency="BRL", quantity=10,
                   captured_at="2026-09-01T00:00:00+00:00", source_url="u",
                   extra={"sector": sector, "entry_class": "Inteira"})


class _WatchCase(unittest.TestCase):
    def setUp(self):
        adapters.ADAPTERS["stub"] = _StubAdapter
        self.addCleanup(adapters.ADAPTERS.pop, "stub", None)
        self.addCleanup(setattr, _StubAdapter, "ROWS", {})

        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.targets = Path(d.name) / "targets"
        self.history = Path(d.name) / "history"
        self.targets.mkdir()
        self.history.mkdir()

    def write_target(self, tid, filters):
        (self.targets / f"{tid}.json").write_text(json.dumps({
            "id": tid, "label": f"label {tid}", "adapter": "stub",
            "params": {}, "filters": filters, "rules": {}, "enabled": True,
        }), encoding="utf-8")

    def run_watch(self):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = watch.main(["--targets", str(self.targets),
                             "--history", str(self.history),
                             "--notifier", "console"])
        return rc, out.getvalue(), err.getvalue()


class TestOneBadTargetDoesNotSilenceTheRest(_WatchCase):
    GOOD = {"extra": {"sector": ["Gramado"]}}
    TYPO = {"extra": {"sectr": ["Gramado"]}}

    def test_a_typod_filter_costs_only_its_own_target(self):
        """`a-bad` sorts FIRST -- the shape that made one bad night take the rest."""
        self.write_target("a-bad", self.TYPO)
        self.write_target("z-good", self.GOOD)
        _StubAdapter.ROWS = {"a-bad": [_reading("a-bad")], "z-good": [_reading("z-good")]}

        rc, out, err = self.run_watch()

        # Isolation first: it is the defect under test, so it should be the assertion
        # that names the failure if this ever regresses.
        self.assertIn("z-good", out, "the target after the bad one was never polled")
        self.assertIn("1 listings seen, 1 after filters", out)
        self.assertEqual(rc, 2, "a real config error must still exit 2")
        self.assertIn("CONFIG ERROR", err)

    def test_known_bad_leg_a_clean_run_over_the_same_two_targets(self):
        """Without this control, 'z-good ran' proves nothing about the isolation --
        it would read the same on a run that never reached a config error at all."""
        self.write_target("a-good", self.GOOD)
        self.write_target("z-good", self.GOOD)
        _StubAdapter.ROWS = {"a-good": [_reading("a-good")], "z-good": [_reading("z-good")]}

        rc, out, err = self.run_watch()

        self.assertEqual(rc, 0)
        self.assertNotIn("CONFIG ERROR", err)
        self.assertIn("a-good", out)
        self.assertIn("z-good", out)


class TestAnEmptyNightIsNotAConfigError(_WatchCase):
    """The production failure of 2026-09-01, end to end."""

    SHIPPED = {"min_quantity": 1, "extra": {"sector": ["Gramado"], "entry_class": None}}

    def test_a_sold_out_night_leaves_the_run_clean(self):
        self.write_target("a-empty", self.SHIPPED)
        self.write_target("z-good", self.SHIPPED)
        _StubAdapter.ROWS = {"a-empty": [], "z-good": [_reading("z-good")]}

        rc, out, err = self.run_watch()

        self.assertEqual(rc, 0, "sold out is data, not a config error")
        self.assertIn("nothing on sale", out)
        self.assertIn("z-good", out)
        self.assertNotIn("CONFIG ERROR", err)


if __name__ == "__main__":
    unittest.main()
