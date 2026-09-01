import json
import unittest

from pricewatch.adapters.buyticketbrasil import BuyTicketBrasilAdapter
from pricewatch.filters import apply_filters
from pricewatch.models import AdapterError
from tests.helpers import fixture_body, make_target


class TestParse(unittest.TestCase):
    """Parsed against the real 2026-09-01 capture, not a hand-written sample."""

    def setUp(self):
        self.a = BuyTicketBrasilAdapter()
        self.t = make_target()
        self.readings = self.a.parse(fixture_body(), self.t, "https://example.test/")

    def test_finds_every_combination(self):
        self.assertEqual(len(self.readings), 19)

    def test_prices_are_centavos_not_reais(self):
        by_item = {r.item: r for r in self.readings}
        self.assertEqual(by_item["Gramado || Inteira"].price_cents, 28600)
        self.assertEqual(by_item["Gramado || Inteira"].quantity, 208)

    def test_carries_sector_and_class_for_filtering(self):
        r = next(r for r in self.readings if r.item == "Gramado || Inteira")
        self.assertEqual(r.extra["sector"], "Gramado")
        self.assertEqual(r.extra["entry_class"], "Inteira")
        self.assertTrue(r.extra["id_ref"])

    def test_gramado_filter_selects_seven(self):
        got = apply_filters(self.readings, {"extra": {"sector": ["Gramado"]}})
        self.assertEqual(len(got), 7)
        self.assertTrue(all(r.extra["sector"] == "Gramado" for r in got))

    def test_cheapest_gramado_matches_the_recon(self):
        got = apply_filters(self.readings, {"extra": {"sector": ["Gramado"]}})
        self.assertEqual(min(r.price_cents for r in got), 27500)


class TestFailureModes(unittest.TestCase):
    """The guards only mean something if the known-bad input actually trips them."""

    def setUp(self):
        self.a = BuyTicketBrasilAdapter()
        self.t = make_target()

    def test_missing_payload_raises_rather_than_returning_empty(self):
        with self.assertRaises(AdapterError):
            self.a.parse("<html>totally different site</html>", self.t, "u")

    def test_empty_matriz_is_data_not_failure(self):
        """Sold out must stay distinguishable from broken."""
        got = self.a.parse('x:{"matriz_preco":{}}', self.t, "u")
        self.assertEqual(got, [])

    def test_zero_priced_placeholder_rows_are_dropped(self):
        body = json.dumps({"matriz_preco": {
            "Gramado||Meia aposentado": {"preco_min": 0, "disponivel": 0},
            "Gramado||Inteira": {"preco_min": 28600, "disponivel": 208},
        }})
        got = self.a.parse(body, self.t, "u")
        self.assertEqual([r.item for r in got], ["Gramado || Inteira"])

    def test_malformed_row_is_skipped_not_fatal(self):
        body = json.dumps({"matriz_preco": {
            "Gramado||Broken": {"disponivel": 3},
            "Gramado||Inteira": {"preco_min": 28600, "disponivel": 208},
        }})
        self.assertEqual(len(self.a.parse(body, self.t, "u")), 1)

    def test_build_url_carries_the_date_and_venue_ids(self):
        url = self.a.build_url(self.t)
        self.assertIn("data=1788570000000", url)
        self.assertIn("evento_local=1765323377313x720803947984191500", url)
        self.assertTrue(url.startswith("https://buyticketbrasil.com/evento/rockinrio2026?"))


if __name__ == "__main__":
    unittest.main()
