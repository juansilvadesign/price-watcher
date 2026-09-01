"""Notification sinks.

v1 ships the console sink only. The interface exists so a Telegram/email sink can
be added later without touching the core: implement `send()` and register it in
`SINKS`. Nothing here is stubbed out with a fake implementation -- an untested
notifier that silently no-ops is worse than not having one.
"""

from __future__ import annotations

from typing import Protocol

from .models import Alert, fmt_brl


class Notifier(Protocol):
    def send(self, target_label: str, alerts: list[Alert]) -> None: ...


class ConsoleNotifier:
    """Prints alerts to stdout."""

    def send(self, target_label: str, alerts: list[Alert]) -> None:
        for a in alerts:
            print(f"  !! [{a.rule}] {a.headline}")
            print(f"     {a.detail}")
            print(f"     {a.reading.source_url}")


SINKS: dict[str, type] = {
    "console": ConsoleNotifier,
}


def build(name: str) -> Notifier:
    if name not in SINKS:
        raise KeyError(f"unknown notifier {name!r}; available: {sorted(SINKS)}")
    return SINKS[name]()
