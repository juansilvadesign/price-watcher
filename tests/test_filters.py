import unittest

from pricewatch.filters import FilterError, apply_filters
from pricewatch.models import Reading


def r(item, cents, qty, **extra):
    return Reading(target_id="t", site="s", item=item, price_cents=cents, currency="BRL",
                   quantity=qty, captured_at="2026-09-01T00:00:00+00:00", source_url="u",
                   extra=extra)


ROWS = [
    r("Gramado || Inteira", 28600, 208, sector="Gramado", entry_class="Inteira"),
    r("Gramado || Meia Idoso", 27500, 1, sector="Gramado", entry_class="Meia Idoso"),
    r("Comfort Zone || Inteira", 66000, 10, sector="Comfort Zone", entry_class="Inteira"),
    r("Vip - Club One || Inteira", 253000, 0, sector="Vip - Club One", entry_class="Inteira"),
]


class TestFilters(unittest.TestCase):
    def test_no_filters_is_passthrough(self):
        self.assertEqual(len(apply_filters(ROWS, {})), 4)

    def test_min_quantity_drops_sold_out(self):
        got = apply_filters(ROWS, {"min_quantity": 1})
        self.assertEqual(len(got), 3)

    def test_sector_filter(self):
        got = apply_filters(ROWS, {"extra": {"sector": ["Gramado"]}})
        self.assertEqual({x.extra["sector"] for x in got}, {"Gramado"})

    def test_null_value_means_all(self):
        """entry_class: null is a documented no-op, not an accident."""
        got = apply_filters(ROWS, {"min_quantity": 0, "extra": {"entry_class": None}})
        self.assertEqual(len(got), 4)

    def test_min_quantity_defaults_to_one(self):
        """Pinned deliberately: any `filters` block silently drops sold-out rows.

        That default is wanted -- a qty-0 row still carries a price, and left in it
        would win every min() and drag thresholds down to a ticket nobody can buy --
        but an implicit default is indistinguishable from a decision, so it is
        asserted here and written explicitly in every shipped target file.
        """
        self.assertEqual(len(apply_filters(ROWS, {"extra": {"entry_class": None}})), 3)

    def test_unknown_field_is_fatal_not_silently_empty(self):
        """A typo'd filter would otherwise look exactly like a sold-out market."""
        with self.assertRaises(FilterError) as cm:
            apply_filters(ROWS, {"extra": {"sectr": ["Gramado"]}})
        self.assertIn("discard everything", str(cm.exception))

    def test_no_match_on_a_real_field_is_legitimate_empty(self):
        got = apply_filters(ROWS, {"extra": {"sector": ["Camarote"]}})
        self.assertEqual(got, [])

    def test_exclude_removes_named_values(self):
        got = apply_filters(ROWS, {"min_quantity": 0,
                                   "extra_exclude": {"sector": ["Vip - Club One"]}})
        self.assertEqual(len(got), 3)
        self.assertNotIn("Vip - Club One", {x.extra["sector"] for x in got})

    def test_exclude_on_an_unknown_field_is_fatal(self):
        """An exclusion that matches nothing excludes nothing -- silently."""
        with self.assertRaises(FilterError):
            apply_filters(ROWS, {"extra_exclude": {"nope": ["x"]}})

    def test_empty_exclude_list_is_a_noop(self):
        self.assertEqual(len(apply_filters(ROWS, {"min_quantity": 0,
                                                  "extra_exclude": {"sector": []}})), 4)

    def test_combined_filters(self):
        got = apply_filters(ROWS, {"min_quantity": 5, "extra": {"sector": ["Gramado"]}})
        self.assertEqual([x.item for x in got], ["Gramado || Inteira"])


if __name__ == "__main__":
    unittest.main()
