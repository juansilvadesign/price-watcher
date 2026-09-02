"""Alert rules.

Every rule is evaluated against the history as it stood BEFORE this run's readings
were appended -- otherwise the current run is its own baseline and no rule can ever
fire. `watch.py` enforces that ordering.

Every rule is edge-triggered: they fire on a transition, not on a state. A
level-triggered "still below your ceiling" would re-alert on every cron tick and
train you to ignore it.

Two kinds of rule live here and they must not be confused. `lowest_ever`,
`lowest_in_window` and `drop_pct` are RELATIVE: they compare against a baseline
built from history. `below_threshold` and `critical_price` are ABSOLUTE: they
compare against a number you wrote down. Only the absolute kind is safe against a
mispriced reading, which is exactly why `critical_price` owns the anomaly band and
the relative rules are excluded from it -- see `_anomaly_floor`.
"""

from __future__ import annotations

import datetime as _dt

# No formatting here any more: a rule emits a message key and its parameters,
# and `messages.py` turns those into a sentence -- once per language -- at
# delivery time. One firing can reach recipients who read different languages.
from .models import Alert, Reading


def _cheapest(readings: list[Reading]) -> Reading | None:
    return min(readings, key=lambda r: r.price_cents) if readings else None


def _anomaly_floor(target) -> int | None:
    """The `critical_price` ceiling, when that rule is armed -- else None.

    Below this price a reading is treated as anomalous rather than cheap. It is
    excluded from every baseline (so a one-minute mispricing cannot ratchet
    `lowest_ever` shut) and the two "is this a new low?" rules stay silent on it,
    because the band belongs to `critical_price`, which alerts on it immediately.

    Disabling `critical_price` disables the protection with it: one switch, so a
    target cannot end up alerting on anomalies while still baselining them.
    """
    cfg = target.rules.get("critical_price")
    if not cfg or not cfg.get("enabled", False):
        return None
    return cfg.get("price_cents")


def _cheapest_legit(readings: list[Reading], floor: int | None) -> Reading | None:
    """The cheapest reading that is not anomalous.

    ⚠️ Filtering the READINGS, not just the baseline, is load-bearing. Taking the
    cheapest first and rejecting it if it is sub-floor would mute the rule for the
    whole run -- so a glitched `Inteira` at R$ 66,00 would hide a genuine new low on
    `Meia Estudante` sitting right above the floor, for as long as the glitch lasted.
    """
    if floor is None:
        return _cheapest(readings)
    return _cheapest([r for r in readings if r.price_cents >= floor])


def lowest_ever(target, readings, history) -> Alert | None:
    """Fires when this run beats every price ever recorded for the target.

    Silent on the very first run: with no prior history every price is trivially a
    record, and an alert that always fires the first time teaches nothing.
    """
    floor = _anomaly_floor(target)
    now = _cheapest_legit(readings, floor)
    if now is None:
        return None
    prior = history.min_price_cents(target.id, floor_cents=floor)
    if prior is None:
        return None
    if now.price_cents < prior:
        return Alert(
            target_id=target.id,
            rule="lowest_ever",
            message_key="lowest_ever",
            params={"item": now.item, "price": now.price_cents,
                    "qty": now.quantity, "prior": prior},
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
        message_key="below_threshold",
        params={"item": now.item, "price": now.price_cents,
                "qty": now.quantity, "ceiling": ceiling},
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
        message_key="drop_pct",
        params={"item": now.item, "price": now.price_cents, "qty": now.quantity,
                "prev": prev, "moved": moved, "pct": pct},
        reading=now,
    )


def price_changed(target, readings, history) -> Alert | None:
    """Fires whenever the cheapest price moved at all since the previous run.

    The most sensitive rule here, and the one most able to become noise: on a resale
    market polled every 30 minutes it can fire several times a day. `direction`
    narrows it to the moves you would actually act on, and `min_delta_brl` filters
    out churn that is not worth a notification.

    Still edge-triggered — it compares against the previous run, so a price that
    holds steady stays silent no matter how far it is from any threshold.
    """
    cfg = target.rules["price_changed"]
    direction = cfg["direction"]
    min_delta = cfg.get("min_delta_cents", 1)

    now = _cheapest(readings)
    prev = history.last_run_min_cents(target.id)
    if now is None or prev is None:
        return None

    delta = now.price_cents - prev
    if abs(delta) < min_delta:
        return None
    if direction == "down" and delta >= 0:
        return None
    if direction == "up" and delta <= 0:
        return None

    moved = abs(delta) / prev * 100.0 if prev else 0.0
    return Alert(
        target_id=target.id,
        rule="price_changed",
        message_key="price_changed.down" if delta < 0 else "price_changed.up",
        params={"item": now.item, "price": now.price_cents, "qty": now.quantity,
                "prev": prev, "delta": abs(delta), "moved": moved},
        reading=now,
    )


def lowest_in_window(target, readings, history) -> Alert | None:
    """Fires when this run beats everything standing in the last N hours.

    `lowest_ever` answers "is this the best price ever?". On the day you actually buy,
    the question is "is this the best price *right now*?" -- and the two diverge in a
    predictable direction, because `lowest_ever` **ratchets shut**. Every record it
    sets raises its own bar, so the longer it runs the less likely it is to speak, and
    the day you need it most is the day its bar is highest. A rolling window cannot
    ratchet: its baseline expires.

    Edge-triggered like every other rule here -- see `History.min_price_cents_since`
    for the carry-forward that keeps it that way over a change log.
    """
    cfg = target.rules["lowest_in_window"]
    hours = cfg["window_hours"]
    floor = _anomaly_floor(target)
    now = _cheapest_legit(readings, floor)
    if now is None:
        return None
    cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=hours)
    prior = history.min_price_cents_since(target.id, cutoff, floor_cents=floor)
    if prior is None:
        return None  # no history yet -- silent for the same reason lowest_ever is
    if now.price_cents >= prior:
        return None
    return Alert(
        target_id=target.id,
        rule="lowest_in_window",
        message_key="lowest_in_window",
        params={"item": now.item, "price": now.price_cents, "qty": now.quantity,
                "hours": hours, "prior": prior},
        reading=now,
    )


def critical_price(target, readings, history) -> Alert | None:
    """Fires immediately when the price falls BELOW X -- the anomaly band.

    The standard rules ask "is this a new low?" against a baseline. That question is
    the wrong one for a price so far below the market that it is probably a listing
    error: it is worth knowing about *now*, and it must never become the baseline.
    Both halves matter, and the second is the one that bites. On 2026-09-02 a single
    R$ 66,00 `Gramado || Inteira` -- one run, gone the next minute -- set the
    `lowest_ever` record for 04/09. That record has no expiry, so the rule was
    permanently dead on the night it was built for, and the 6h window was muted with
    it. See `_anomaly_floor` for the exclusion that prevents the repeat.

    Cadence: fires on ENTERING the band, then again on each new low inside it, and
    stays silent while a sub-floor price merely holds. Still edge-triggered, so a
    stuck mispricing does not alert once a minute forever -- but a market genuinely
    falling through the floor is reported the whole way down.
    """
    cfg = target.rules["critical_price"]
    floor = cfg["price_cents"]
    now = _cheapest(readings)                 # the true cheapest -- anomalies included
    if now is None or now.price_cents >= floor:
        return None

    prev = history.last_run_min_cents(target.id)
    if prev is not None and prev < floor and now.price_cents >= prev:
        # Already in the band and not a new low: the entry alert has been sent and
        # nothing has improved since.
        return None

    entering = prev is None or prev >= floor
    return Alert(
        target_id=target.id,
        rule="critical_price",
        # Two keys, not one sentence with a swapped clause: "is below" / "is a new low
        # below" sits mid-sentence in English and cannot be assumed to survive that
        # position in another language.
        message_key="critical_price.entering" if entering else "critical_price.new_low",
        params={"item": now.item, "price": now.price_cents,
                "qty": now.quantity, "floor": floor},
        reading=now,
    )


def _validate_price_cents(cfg: dict) -> str | None:
    p = cfg.get("price_cents")
    if not isinstance(p, int) or isinstance(p, bool) or p <= 0:
        return f"price_cents must be a positive integer, got {p!r}"
    return None


def _validate_window_hours(cfg: dict) -> str | None:
    h = cfg.get("window_hours")
    # `isinstance(True, int)` is True, so a bare `true` in JSON would otherwise sail
    # through as a 1-hour window -- configured, plausible-looking, and not what anyone
    # wrote it to mean.
    if isinstance(h, bool) or not isinstance(h, (int, float)) or h <= 0:
        return f"window_hours must be a positive number, got {h!r}"
    return None


def _validate_direction(cfg: dict) -> str | None:
    if cfg.get("direction") not in ("any", "down", "up"):
        return f"direction must be one of any/down/up, got {cfg.get('direction')!r}"
    return None


#: Rule name -> (evaluator, required config keys, optional value validator). The
#: registry validates against this table, so a rule enabled without its parameter —
#: or with a nonsense value — fails loudly at load time instead of silently never
#: firing.
RULES = {
    "lowest_ever":      (lowest_ever,      (),                 None),
    "below_threshold":  (below_threshold,  ("price_cents",),   None),
    "drop_pct":         (drop_pct,         ("pct",),           None),
    "price_changed":    (price_changed,    ("direction",),     _validate_direction),
    "lowest_in_window": (lowest_in_window, ("window_hours",),  _validate_window_hours),
    "critical_price":   (critical_price,   ("price_cents",),   _validate_price_cents),
}


def evaluate(target, readings, history) -> list[Alert]:
    alerts = []
    for name, cfg in target.rules.items():
        if not cfg.get("enabled", False):
            continue
        fn = RULES[name][0]
        alert = fn(target, readings, history)
        if alert is not None:
            alerts.append(alert)
    return alerts
