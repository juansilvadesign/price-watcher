"""Adapter registry. Adding a site = adding a module here + one line in ADAPTERS."""

from __future__ import annotations

from . import buyticketbrasil

ADAPTERS = {
    "buyticketbrasil": buyticketbrasil.BuyTicketBrasilAdapter,
}


def build(name: str):
    if name not in ADAPTERS:
        raise KeyError(f"unknown adapter {name!r}; available: {sorted(ADAPTERS)}")
    return ADAPTERS[name]()
