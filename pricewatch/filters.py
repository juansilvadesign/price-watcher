"""Target-side filtering, applied by the harness to whatever the adapter returned.

Adapters report everything they can see; targets decide what they care about. That
split keeps the adapter reusable across people who want different slices of the
same page.
"""

from __future__ import annotations

from .models import Reading


class FilterError(ValueError):
    """A filter that cannot match anything, structurally. Always fatal."""


def apply_filters(readings: list[Reading], filters: dict, where: str = "target") -> list[Reading]:
    """Return the subset of `readings` a target cares about.

    An empty result is legitimate data ("the sector is sold out"). A filter naming
    a field no reading carries is NOT -- that is a typo that would silently discard
    every reading and look like a sold-out market forever, so it raises.
    """
    if not filters:
        return list(readings)

    out = list(readings)

    min_qty = filters.get("min_quantity", 1)
    if min_qty is not None:
        out = [r for r in out if r.quantity >= min_qty]

    for field, allowed in (filters.get("extra") or {}).items():
        if allowed is None:
            continue  # explicit "all values" -- a documented no-op, not a typo
        if not any(field in r.extra for r in readings):
            seen = sorted({k for r in readings for k in r.extra})
            raise FilterError(
                f"{where}: filter field 'extra.{field}' appears on none of the "
                f"{len(readings)} readings this adapter returned. Fields present: {seen}. "
                f"Refusing to run -- this filter would discard everything and look "
                f"like a sold-out market."
            )
        allowed_set = set(allowed)
        out = [r for r in out if r.extra.get(field) in allowed_set]

    # Symmetric deny-list. `extra` answers "only these"; `extra_exclude` answers
    # "anything but these", which is the shape you want when the exceptions are
    # few and the allowed set is long or changes upstream.
    for field, denied in (filters.get("extra_exclude") or {}).items():
        if not denied:
            continue
        if not any(field in r.extra for r in readings):
            seen = sorted({k for r in readings for k in r.extra})
            raise FilterError(
                f"{where}: exclude field 'extra.{field}' appears on none of the "
                f"{len(readings)} readings this adapter returned. Fields present: {seen}. "
                f"Refusing to run -- an exclusion that matches nothing silently "
                f"excludes nothing."
            )
        denied_set = set(denied)
        out = [r for r in out if r.extra.get(field) not in denied_set]

    return out
