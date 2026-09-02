"""Alert text, in every language a recipient might read it in.

A subscriber's language is chosen when you approve them (`--lang pt-BR`), so one firing
of one rule has to produce as many renderings as there are languages among its
recipients. That is why a rule no longer writes a sentence: it emits a **message key
and its parameters**, and the sentence is built here, once per language, at delivery.

⭐ **`Alert.headline` / `Alert.detail` are the en-US rendering of this same catalog** --
not a second copy of the English text. Console and toast are yours alone and stay
English by reading those properties, and English is written down in exactly one place.
Two sets of f-strings would drift the first time a rule's wording changed, and nobody
would notice: the drift is only visible to the person reading the *other* language.

⛔ **The catalog is validated at import**, not by a test somebody has to remember to run.
Three things are checked, and each is a defect that would otherwise surface as a warning
at 3am on the one alert that mattered -- `_subscriber_failed` catches every exception
from a send, classifies a `KeyError` as transient (it carries no `error_code`), and
warns about it forever without disabling anything or touching the exit code:

* **Every key exists in every language.** Otherwise that friend receives nothing, on
  every run, and the only trace is a line in cron.log.
* **Every language of a key interpolates the same placeholders.** A typo (`{prise}`) is
  the same silent-warning failure; an omission is a sentence that quietly drops the
  quantity or the previous price and still reads perfectly well.
* **Every placeholder has a formatter.** A money value missing from `MONEY` renders as
  raw centavos -- `25000` where the reader expects `R$ 250,00`. That one raises nothing
  anywhere; it is simply wrong.

This file is source code, not user config: a failure here fails in the first test run
that imports the package and cannot reach production without failing in development
first. Refusing to import is therefore the loudest signal available, and costs nothing.
"""

from __future__ import annotations

import string as _string

from .models import fmt_brl

#: The language everything falls back to: the owner's, and the one console and toast
#: are written in. Adding a language means adding a complete column to `CATALOG` --
#: the import-time check below refuses a partial one.
DEFAULT_LANG = "en-US"

#: The closed set. `subscribers.py` refuses anything else rather than defaulting to
#: English, because a silently-English friend is indistinguishable from a correctly
#: configured one -- and the person who would notice is the one who cannot read it.
LANGS = ("en-US", "pt-BR")

#: Placeholders whose value is integer centavos. `fmt_brl` already writes pt-BR
#: grouping (R$ 12.345,67), so money reads identically in both languages -- and the
#: money invariant, one division by 100 in one place, is untouched by any of this.
MONEY = frozenset({"price", "prior", "prev", "ceiling", "floor", "delta"})

#: Plain numbers, with the format spec each is written at. Their DECIMAL SEPARATOR is
#: locale-specific, which is the only reason they are listed rather than passed through.
#: `moved` is a measured move (one decimal); `pct` and `hours` are configured values
#: printed at their natural width, so 5.0 shows as "5" and 1.5 as "1.5" / "1,5".
NUMERIC_SPECS = {"moved": ".1f", "pct": "g", "hours": "g"}

#: Interpolated verbatim. `item` is third-party text off the watched page; it is escaped
#: by the sink, at the sink, AFTER rendering -- never here, or Telegram's HTML entities
#: would be escaped a second time and the toast would see them as literal text.
PLAIN = frozenset({"item", "qty"})


#: key -> (headline, detail), per language. Keys that end in a variant (`.down`,
#: `.entering`) exist because the branch changes a WORD, and a word is exactly what a
#: translation may not be able to slot into a shared sentence.
CATALOG: dict[str, dict[str, tuple[str, str]]] = {
    "en-US": {
        "lowest_ever": (
            "NEW LOWEST — {price}",
            "{item} at {price} (qty {qty}) beats the previous record of {prior}.",
        ),
        "below_threshold": (
            "UNDER {ceiling} — {price}",
            "{item} at {price} (qty {qty}) is at or below your ceiling of {ceiling}.",
        ),
        "drop_pct": (
            "DROP {moved}% — {price}",
            "{item} fell from {prev} to {price} ({moved}%, threshold {pct}%), qty {qty}.",
        ),
        "price_changed.down": (
            "DOWN {delta} — now {price}",
            "{item} moved {prev} → {price} (down {moved}%), qty {qty}.",
        ),
        "price_changed.up": (
            "UP {delta} — now {price}",
            "{item} moved {prev} → {price} (up {moved}%), qty {qty}.",
        ),
        "lowest_in_window": (
            "{hours}h LOW — {price}",
            "{item} at {price} (qty {qty}) is the cheapest in {hours}h, beating {prior}.",
        ),
        "critical_price.entering": (
            "CRITICAL {price} — under {floor}",
            "{item} at {price} (qty {qty}) is below the anomaly floor of {floor}. "
            "Verify before acting — this far under market is often a listing error, "
            "and it is deliberately excluded from every baseline.",
        ),
        "critical_price.new_low": (
            "CRITICAL {price} — under {floor}",
            "{item} at {price} (qty {qty}) is a new low below the anomaly floor of "
            "{floor}. Verify before acting — this far under market is often a listing "
            "error, and it is deliberately excluded from every baseline.",
        ),
        "test_notify": (
            "TEST — {price}",
            "Synthetic alert from price-watcher. If you received this, you are on the "
            "list and delivery works.",
        ),
    },
    "pt-BR": {
        "lowest_ever": (
            "NOVA MÍNIMA — {price}",
            "{item} a {price} (qtd {qty}) supera o recorde anterior de {prior}.",
        ),
        "below_threshold": (
            "ABAIXO DE {ceiling} — {price}",
            "{item} a {price} (qtd {qty}) está no seu teto de {ceiling} ou abaixo dele.",
        ),
        "drop_pct": (
            "QUEDA DE {moved}% — {price}",
            "{item} caiu de {prev} para {price} ({moved}%, limite {pct}%), qtd {qty}.",
        ),
        "price_changed.down": (
            "QUEDA DE {delta} — agora {price}",
            "{item} foi de {prev} para {price} (queda de {moved}%), qtd {qty}.",
        ),
        "price_changed.up": (
            "ALTA DE {delta} — agora {price}",
            "{item} foi de {prev} para {price} (alta de {moved}%), qtd {qty}.",
        ),
        "lowest_in_window": (
            "MÍNIMA EM {hours}h — {price}",
            "{item} a {price} (qtd {qty}) é a mais barata em {hours}h, superando {prior}.",
        ),
        "critical_price.entering": (
            "CRÍTICO {price} — abaixo de {floor}",
            "{item} a {price} (qtd {qty}) está abaixo do piso de anomalia de {floor}. "
            "Confirme antes de agir — um preço tão abaixo do mercado costuma ser erro "
            "de anúncio, e ele é excluído de propósito de toda base de comparação.",
        ),
        "critical_price.new_low": (
            "CRÍTICO {price} — abaixo de {floor}",
            "{item} a {price} (qtd {qty}) é uma nova mínima abaixo do piso de anomalia "
            "de {floor}. Confirme antes de agir — um preço tão abaixo do mercado "
            "costuma ser erro de anúncio, e ele é excluído de propósito de toda base "
            "de comparação.",
        ),
        "test_notify": (
            "TESTE — {price}",
            "Alerta sintético do price-watcher. Se você recebeu isto, está na lista e "
            "a entrega está funcionando.",
        ),
    },
}

SLOTS = ("headline", "detail")


class CatalogError(RuntimeError):
    """The message catalog is structurally broken. Raised at import, never caught."""


def placeholders(template: str) -> set[str]:
    """The `{name}` fields a template interpolates. Exposed so a test can pin one."""
    return {field for _, field, _, _ in _string.Formatter().parse(template) if field}


def _validate() -> None:
    known = MONEY | set(NUMERIC_SPECS) | PLAIN

    declared, present = set(LANGS), set(CATALOG)
    if declared != present:
        raise CatalogError(
            f"LANGS and CATALOG disagree: declared-but-absent {sorted(declared - present)}, "
            f"present-but-undeclared {sorted(present - declared)}")

    base = CATALOG[DEFAULT_LANG]
    for lang in LANGS:
        missing, extra = set(base) - set(CATALOG[lang]), set(CATALOG[lang]) - set(base)
        if missing or extra:
            raise CatalogError(
                f"{lang} does not cover the same keys as {DEFAULT_LANG}: "
                f"missing {sorted(missing)}, unexpected {sorted(extra)}")

    for key, reference in base.items():
        for lang in LANGS:
            for slot, ref, got in zip(SLOTS, reference, CATALOG[lang][key]):
                want, have = placeholders(ref), placeholders(got)
                if want != have:
                    raise CatalogError(
                        f"{lang} {key}.{slot} interpolates {sorted(have)}, but "
                        f"{DEFAULT_LANG} interpolates {sorted(want)}")
                unknown = have - known
                if unknown:
                    raise CatalogError(
                        f"{lang} {key}.{slot} uses {sorted(unknown)}, which no formatter "
                        f"covers — add to MONEY, NUMERIC_SPECS or PLAIN. Left alone, a "
                        f"money value renders as raw centavos and nothing raises.")


_validate()


def _display(params: dict, lang: str) -> dict[str, str]:
    """Params as the strings this language writes them with."""
    out: dict[str, str] = {}
    for name, value in params.items():
        if name in MONEY:
            out[name] = fmt_brl(value)
        elif name in NUMERIC_SPECS:
            shown = format(value, NUMERIC_SPECS[name])
            out[name] = shown.replace(".", ",") if lang == "pt-BR" else shown
        else:
            out[name] = str(value)
    return out


def render(key: str, params: dict, lang: str = DEFAULT_LANG) -> tuple[str, str]:
    """`(headline, detail)` for one alert, in one language.

    Returns **plain text**. Escaping belongs to the sink and happens after this: the
    Telegram sink escapes for HTML, the toast sink for XML-inside-PowerShell, and the
    console for nothing. Escaping here would double-escape in the first two.
    """
    if lang not in CATALOG:
        raise ValueError(f"unknown language {lang!r}; known: {', '.join(LANGS)}")
    if key not in CATALOG[lang]:
        raise KeyError(f"no {lang} message for {key!r}; known: {sorted(CATALOG[lang])}")

    shown = _display(params, lang)
    rendered = []
    for slot, template in zip(SLOTS, CATALOG[lang][key]):
        try:
            rendered.append(template.format_map(shown))
        except KeyError as e:
            raise KeyError(
                f"{lang} {key}.{slot} needs {e.args[0]!r}, which the rule did not "
                f"supply; got {sorted(params)}") from None
    return rendered[0], rendered[1]
