"""The adapter contract.

An adapter is the only site-specific code in the project. It answers one question:
given a target's params, what is on sale right now and for how much?

    fetch(target) -> list[Reading]

Contract:
  * Prices are integer centavos. Never floats.
  * Raise `AdapterError` when the site cannot be read or its payload shape is gone.
  * Return `[]` ONLY for a genuine "nothing on sale" -- never to paper over a
    parse failure. The caller distinguishes the two and an empty list is treated
    as real data.
  * Do not filter. The harness applies target filters; the adapter reports
    everything it can see.
"""

from __future__ import annotations

from typing import Protocol

from ..models import Reading


class Adapter(Protocol):
    site: str

    def build_url(self, target) -> str: ...
    def fetch(self, target) -> list[Reading]: ...
