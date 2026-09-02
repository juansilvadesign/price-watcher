"""Core data shapes shared by every adapter.

Money is carried as **integer centavos** everywhere inside this package. The first
site adapter (buyticketbrasil) serves `preco_min` in centavos already, and floats
would quietly reintroduce rounding error into threshold comparisons. Conversion to
a human-readable BRL string happens only at the edges (`fmt_brl`).
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field, asdict
from typing import Any


def utcnow_iso() -> str:
    """Timestamp for a reading: ISO-8601, UTC, second precision."""
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def fmt_brl(cents: int) -> str:
    """1234567 -> 'R$ 12.345,67' (pt-BR grouping, no locale dependency)."""
    sign = "-" if cents < 0 else ""
    whole, frac = divmod(abs(int(cents)), 100)
    return f"{sign}R$ {whole:,.0f}".replace(",", ".") + f",{frac:02d}"


class AdapterError(RuntimeError):
    """The adapter could not read the site at all.

    Raised for a transport failure or a payload whose expected shape is gone --
    i.e. "the site changed and this adapter is now blind". It must NEVER be raised
    for a legitimately empty result (everything sold out), because those two states
    have to stay distinguishable: one is a broken watcher, the other is real data.
    """


@dataclass(frozen=True)
class Reading:
    """One price observation for one purchasable line item, at one instant."""

    target_id: str
    site: str
    item: str            # human key, e.g. "Gramado || Inteira"
    price_cents: int
    currency: str
    quantity: int
    captured_at: str
    source_url: str
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def available(self) -> bool:
        return self.quantity > 0

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["available"] = self.available
        return d

    def __str__(self) -> str:
        return f"{self.item:<38} {fmt_brl(self.price_cents):>13}  qty={self.quantity}"


@dataclass(frozen=True)
class Alert:
    """A fired alert rule, ready to hand to a Notifier.

    It carries **what happened**, not a sentence about it: a `message_key` and the
    values that go in it. One firing reaches recipients who read different languages,
    so the sentence cannot be chosen when the rule fires -- only when it is delivered.
    `messages.render` does that, once per language, inside the sink.

    `headline` and `detail` are still here, and still English: they are the en-US
    rendering of that same catalog, not a second copy of the text. Console and toast
    are yours alone, read them, and did not change.
    """

    target_id: str
    rule: str
    message_key: str
    params: dict[str, Any]
    reading: Reading

    def render(self, lang: str | None = None) -> tuple[str, str]:
        # Imported here, not at module scope: `messages` needs `fmt_brl` from this
        # module, so a top-level import would be a cycle. By the time any alert is
        # rendered both modules are fully loaded, and this costs one dict lookup.
        from . import messages
        return messages.render(self.message_key, self.params, lang or messages.DEFAULT_LANG)

    @property
    def headline(self) -> str:
        return self.render()[0]

    @property
    def detail(self) -> str:
        return self.render()[1]
