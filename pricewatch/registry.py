"""Target registry: one JSON file per watch target in `targets/`.

Adding a target is adding a file. Adding a *site* is adding one adapter module --
that split is the whole point of the hub.

Validation is deliberately strict and happens at load time. A target that enables
`below_threshold` without giving a price, or names an adapter that does not exist,
raises here rather than running forever and never firing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import rules as _rules

#: Rules whose threshold is hand-written in BRL and stored internally in centavos.
#: Money is integer centavos everywhere inside the package; this is the only door.
_BRL_PRICE_RULES = ("below_threshold", "critical_price")


class ConfigError(ValueError):
    """A target file is malformed. Always fatal -- never warn and continue."""


@dataclass(frozen=True)
class Target:
    id: str
    label: str
    adapter: str
    params: dict[str, Any]
    filters: dict[str, Any] = field(default_factory=dict)
    rules: dict[str, dict] = field(default_factory=dict)
    enabled: bool = True
    path: Path | None = None


def _require(d: dict, key: str, where: str, typ=None):
    if key not in d:
        raise ConfigError(f"{where}: missing required key {key!r}")
    val = d[key]
    if typ is not None and not isinstance(val, typ):
        raise ConfigError(f"{where}: {key!r} must be {typ.__name__}, got {type(val).__name__}")
    return val


def _normalise_rules(raw: dict, where: str) -> dict[str, dict]:
    """Validate rule config and convert human BRL into internal centavos."""
    out: dict[str, dict] = {}
    for name, cfg in raw.items():
        if name not in _rules.RULES:
            raise ConfigError(f"{where}: unknown rule {name!r}; known: {sorted(_rules.RULES)}")
        if not isinstance(cfg, dict):
            raise ConfigError(f"{where}: rule {name!r} must be an object")
        cfg = dict(cfg)

        # Targets are hand-edited, so thresholds are written in BRL and converted here.
        if name in _BRL_PRICE_RULES and "price_brl" in cfg:
            brl = cfg.pop("price_brl")
            # `isinstance(True, int)` is True, so a bare `true` would convert to
            # R$ 1,00 -- a floor that reads as configured and matches nothing. The
            # same trap `_validate_window_hours` guards, one type earlier: after
            # conversion the bool is an ordinary 100 and no later check can see it.
            if isinstance(brl, bool) or not isinstance(brl, (int, float)) or brl <= 0:
                raise ConfigError(
                    f"{where}: rule {name!r}: price_brl must be a positive number, got {brl!r}")
            cfg["price_cents"] = int(round(float(brl) * 100))
        if name == "price_changed" and "min_delta_brl" in cfg:
            cfg["min_delta_cents"] = max(1, int(round(float(cfg.pop("min_delta_brl")) * 100)))

        if cfg.get("enabled", False):
            _, required, validator = _rules.RULES[name]
            for key in required:
                if cfg.get(key) is None:
                    raise ConfigError(
                        f"{where}: rule {name!r} is enabled but {key!r} is missing. "
                        f"An enabled rule with no parameter never fires and looks healthy "
                        f"-- refusing to load it."
                    )
            if validator is not None:
                problem = validator(cfg)
                if problem:
                    raise ConfigError(f"{where}: rule {name!r}: {problem}")
        out[name] = cfg
    return out


def load_target(path: Path) -> Target:
    where = path.name
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"{where}: invalid JSON -- {e}") from e

    target_id = _require(raw, "id", where, str)
    if target_id != path.stem:
        raise ConfigError(f"{where}: id {target_id!r} must match the filename stem {path.stem!r}")

    return Target(
        id=target_id,
        label=_require(raw, "label", where, str),
        adapter=_require(raw, "adapter", where, str),
        params=_require(raw, "params", where, dict),
        filters=raw.get("filters", {}) or {},
        rules=_normalise_rules(raw.get("rules", {}) or {}, where),
        enabled=bool(raw.get("enabled", True)),
        path=path,
    )


def load_targets(root: Path, only: list[str] | None = None) -> list[Target]:
    root = Path(root)
    if not root.is_dir():
        raise ConfigError(f"targets directory not found: {root}")
    targets = [load_target(p) for p in sorted(root.glob("*.json"))]
    if only:
        known = {t.id for t in targets}
        for want in only:
            if want not in known:
                raise ConfigError(f"no such target {want!r}; known: {sorted(known)}")
        targets = [t for t in targets if t.id in only]
    return targets
