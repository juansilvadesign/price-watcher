"""The message catalog: its structure, its formatting, and its refusals.

Almost everything here is a **known-bad leg**. The catalog's own guards run at import,
so on a healthy tree they are invisible -- these tests are the only place the tree is
ever unhealthy, and therefore the only proof the guards have teeth.

The failure they all guard against has one shape: an alert that renders, delivers, and
is wrong, for the one recipient who cannot tell you so.
"""

import unittest
from unittest import mock

from pricewatch import messages, rules
from pricewatch.messages import (CATALOG, DEFAULT_LANG, LANGS, CatalogError,
                                 placeholders, render)

#: Every parameter any message interpolates, at a plausible value. Rendering the whole
#: catalog against one row is what proves no template needs something no rule supplies.
EVERY_PARAM = {"item": "Gramado || Inteira", "price": 25000, "prior": 26000,
               "prev": 27000, "ceiling": 23000, "floor": 22000, "delta": 200,
               "moved": 7.46, "pct": 5.0, "qty": 3, "hours": 6}


def broken(lang, key, slot=None, template=None):
    """A copy of the catalog with one template replaced -- or one key removed."""
    cat = {lg: dict(keys) for lg, keys in CATALOG.items()}
    if slot is None:
        del cat[lang][key]
    else:
        entry = list(cat[lang][key])
        entry[messages.SLOTS.index(slot)] = template
        cat[lang][key] = tuple(entry)
    return cat


class TestCoverage(unittest.TestCase):
    def test_every_key_renders_in_every_language(self):
        for lang in LANGS:
            for key in CATALOG[lang]:
                with self.subTest(lang=lang, key=key):
                    headline, detail = render(key, EVERY_PARAM, lang)
                    self.assertTrue(headline.strip() and detail.strip())
                    # A surviving brace is a placeholder that was never substituted.
                    self.assertNotIn("{", headline + detail)

    def test_every_rule_has_a_message(self):
        """The guard for the NEXT rule somebody adds.

        A rule shipped without a catalog entry raises `KeyError` inside `_deliver`,
        which the subscriber path catches, classifies as transient and warns about --
        so the rule would appear to work and reach nobody. Keys may be exact or
        variant-suffixed (`critical_price.entering`), which is why this is a prefix
        match rather than a set comparison.
        """
        for name in rules.RULES:
            with self.subTest(rule=name):
                self.assertTrue(
                    any(k == name or k.startswith(f"{name}.") for k in CATALOG[DEFAULT_LANG]),
                    f"rule {name!r} has no message in the catalog")

    def test_the_owner_language_is_a_real_column(self):
        self.assertIn(DEFAULT_LANG, CATALOG)
        self.assertIn(DEFAULT_LANG, LANGS)


class TestFormatting(unittest.TestCase):
    def test_money_reads_the_same_in_both_languages(self):
        """`fmt_brl` already writes pt-BR grouping, so money is not a translation
        problem -- and the money invariant stays untouched by i18n."""
        for lang in LANGS:
            self.assertIn("R$ 250,00", render("lowest_ever", EVERY_PARAM, lang)[0])

    def test_pt_br_writes_a_decimal_comma_and_en_us_a_point(self):
        self.assertIn("7.5%", render("drop_pct", EVERY_PARAM, "en-US")[0])
        self.assertIn("7,5%", render("drop_pct", EVERY_PARAM, "pt-BR")[0])

    def test_a_whole_number_keeps_no_decimals_in_either_language(self):
        """`hours` and `pct` are configured values printed at natural width: a 6-hour
        window must not read as "6,0h" just because the language changed."""
        for lang in LANGS:
            self.assertIn("6h", render("lowest_in_window", EVERY_PARAM, lang)[0])

    def test_rendering_returns_plain_text_for_the_sink_to_escape(self):
        """Escaping here would double-escape at the sink, which does it for real."""
        _, detail = render("lowest_ever", {**EVERY_PARAM, "item": "A & B"}, DEFAULT_LANG)
        self.assertIn("A & B", detail)


class TestRefusals(unittest.TestCase):
    def test_an_unknown_language_is_refused(self):
        with self.assertRaises(ValueError) as cm:
            render("lowest_ever", EVERY_PARAM, "pt_br")
        self.assertIn("pt-BR", str(cm.exception), "it names the languages that do exist")

    def test_an_unknown_key_is_refused(self):
        with self.assertRaises(KeyError):
            render("no_such_rule", EVERY_PARAM, DEFAULT_LANG)

    def test_a_missing_param_names_the_key_and_the_slot(self):
        """This one surfaces as a warning about ONE friend, so the message has to carry
        enough to find it without a stack trace."""
        with self.assertRaises(KeyError) as cm:
            render("lowest_ever", {"item": "x", "price": 1, "qty": 1}, DEFAULT_LANG)
        self.assertIn("lowest_ever", str(cm.exception))
        self.assertIn("prior", str(cm.exception))


class TestCatalogValidation(unittest.TestCase):
    """The import-time guards. Each leg FAILS the validator, which is the whole point:
    on a healthy catalog none of these conditions exists to be observed."""

    def assertRefused(self, catalog, *fragments):
        with mock.patch.object(messages, "CATALOG", catalog):
            with self.assertRaises(CatalogError) as cm:
                messages._validate()
        for f in fragments:
            self.assertIn(f, str(cm.exception))

    def test_a_language_missing_a_key_is_refused(self):
        """Left alone: that friend receives nothing, on every run, forever, and the
        only trace is a warning line in cron.log."""
        self.assertRefused(broken("pt-BR", "lowest_ever"), "pt-BR", "lowest_ever")

    def test_a_placeholder_typo_is_refused(self):
        """`{prise}` raises KeyError at send time -- caught, classified transient,
        warned about, never disabling anyone and never touching the exit code."""
        self.assertRefused(
            broken("pt-BR", "lowest_ever", "headline", "NOVA MÍNIMA — {prise}"),
            "pt-BR", "lowest_ever.headline")

    def test_a_dropped_placeholder_is_refused(self):
        """The quiet one: the sentence still reads perfectly, it just no longer says
        what the previous record was."""
        self.assertRefused(
            broken("pt-BR", "lowest_ever", "detail", "{item} a {price} (qtd {qty})."),
            "prior")

    def test_a_placeholder_no_formatter_covers_is_refused(self):
        """The quietest one of all: it raises nothing anywhere. A money value missing
        from MONEY renders as raw centavos -- 25000 where a reader expects R$ 250,00."""
        cat = broken("en-US", "lowest_ever", "headline", "NEW LOWEST — {savings}")
        cat = {**cat, "pt-BR": {**cat["pt-BR"],
                                "lowest_ever": ("NOVA MÍNIMA — {savings}",
                                                cat["pt-BR"]["lowest_ever"][1])}}
        self.assertRefused(cat, "savings", "MONEY")

    def test_a_language_declared_but_absent_is_refused(self):
        with mock.patch.object(messages, "LANGS", ("en-US", "pt-BR", "es-AR")):
            with self.assertRaises(CatalogError) as cm:
                messages._validate()
        self.assertIn("es-AR", str(cm.exception))

    def test_the_shipped_catalog_passes_its_own_validator(self):
        """The control leg. Without it, every assertion above could be passing because
        the validator raises unconditionally."""
        messages._validate()


class TestPlaceholders(unittest.TestCase):
    def test_it_reads_the_names_a_template_interpolates(self):
        self.assertEqual(placeholders("{a} and {b}"), {"a", "b"})
        self.assertEqual(placeholders("no fields here"), set())


if __name__ == "__main__":
    unittest.main()
