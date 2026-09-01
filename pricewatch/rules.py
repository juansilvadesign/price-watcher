"""Alert rules.

Every rule is evaluated against the history as it stood BEFORE this run's readings
were appended -- otherwise the current run is its own baseline and no rule can ever
fire. `watch.py` enforces that ordering.

All three rules are edge-triggered: they fire on a transition, not on a state. A
level-triggered "still below your ceiling" would re-alert on every cron tick and
train you to ignore it.
"""

from __future__ import annotations

from .models import Alert, Reading, fmt_brl


def _cheapest(readings: list[Reading]) -> Reading | None:
    return min(readings, key=lambda r: r.price_cents) if readings else None


def lowest_ever(target, readings, history) -> Alert | None:
    """Fires when this run beats every price ever recorded for the target.

    Silent on the very first run: with no prior history every price is trivially a
    record, and an alert that always fires the first time teaches nothing.
    """
    now = _cheapest(readings)
    if now is None:
        return None
    prior = history.min_price_cents(target.id)
    if prior is None:
        return None
    if now.price_cents < prior:
        return Alert(
            target_id=target.id,
            rule="lowest_ever",
            headline=f"NEW LOWEST — {fmt_brl(now.price_cents)}",
            detail=(f"{now.item} at {fmt_brl(now.price_cents)} (qty {now.quantity}) "
                    f"beats the previous record of {fmt_brl(prior)}."),
            reading=now,
        )
    return None


def below_threshold(target, readings, history) -> Alert | None:
    """Fires when the cheapest crosses from above your ceiling to at-or-below it."""
    cfg = target.rules["below_threshold"]
    ceiling = cfg["price_cents"]
    now = _cheapest(readings)
    if now is None or now.price_cents > ceiling:
        return None
    prev = history.last_run_min_cents(target.id)
    if prev is not None and prev <= ceiling:
        return None  # already below on the previous run -- not a new crossing
    return Alert(
        target_id=target.id,
        rule="below_threshold",
        headline=f"UNDER {fmt_brl(ceiling)} — {fmt_brl(now.price_cents)}",
        detail=(f"{now.item} at {fmt_brl(now.price_cents)} (qty {now.quantity}) "
                f"is at or below your ceiling of {fmt_brl(ceiling)}."),
        reading=now,
    )


def drop_pct(target, readings, history) -> Alert | None:
    """Fires when the cheapest fell by >= N% since the previous run."""
    cfg = target.rules["drop_pct"]
    pct = cfg["pct"]
    now = _cheapest(readings)
    if now is None:
        return None
    prev = history.last_run_min_cents(target.id)
    if prev is None or prev <= 0 or now.price_cents >= prev:
        return None
    moved = (prev - now.price_cents) / prev * 100.0
    if moved < pct:
        return None
    return Alert(
        target_id=target.id,
        rule="drop_pct",
        headline=f"DROP {moved:.1f}% — {fmt_brl(now.price_cents)}",
        detail=(f"{now.item} fell from {fmt_brl(prev)} to {fmt_brl(now.price_cents)} "
                f"({moved:.1f}%, threshold {pct:g}%), qty {now.quantity}."),
        reading=now,
    )


#: Rule name -> (evaluator, required config keys). The registry validates against
#: this table, so a rule enabled without its parameter fails loudly at load time
#: instead of silently never firing.
RULES = {
    "lowest_ever":     (lowest_ever,     ()),
    "below_threshold": (below_threshold, ("price_cents",)),
    "drop_pct":        (drop_pct,        ("pct",)),
}


def evaluate(target, readings, history) -> list[Alert]:
    alerts = []
    for name, cfg in target.rules.items():
        if not cfg.get("enabled", False):
            continue
        fn, _ = RULES[name]
        alert = fn(target, readings, history)
        if alert is not None:
            alerts.append(alert)
    return alerts
