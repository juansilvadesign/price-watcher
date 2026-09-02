"""Append-only JSONL history, one file per target.

Plain text on purpose: greppable, diffable, and readable without this tool --
the same reason the surrounding workspace keeps everything in Markdown and JSON.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

from .models import Reading


class History:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, target_id: str) -> Path:
        return self.root / f"{target_id}.jsonl"

    def append(self, target_id: str, readings: list[Reading]) -> int:
        """Append one run's readings. Returns how many lines were written."""
        if not readings:
            return 0
        path = self.path_for(target_id)
        with path.open("a", encoding="utf-8") as fh:
            for r in readings:
                fh.write(json.dumps(r.to_json(), ensure_ascii=False) + "\n")
        return len(readings)

    def load(self, target_id: str) -> list[dict]:
        path = self.path_for(target_id)
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows

    def last_run_readings(self, target_id: str) -> dict[str, tuple[int, int]]:
        """The most recent recorded run as {item: (price_cents, quantity)}."""
        rows = self.load(target_id)
        if not rows:
            return {}
        last_ts = rows[-1]["captured_at"]
        return {r["item"]: (r["price_cents"], r["quantity"])
                for r in rows if r["captured_at"] == last_ts}

    def append_if_changed(self, target_id: str, readings: list[Reading]) -> bool:
        """Append only when this run differs from the last recorded one.

        At a one-minute poll the overwhelming majority of runs are byte-identical to
        the previous one. Recording them all would reach ~190 MB in twelve days and,
        worse, force every later run to re-parse hundreds of thousands of lines to
        answer `min_price_cents` — the watcher would get slower the longer it ran.

        Skipping unchanged runs makes the file a **change log**: every line in it is a
        moment the market actually moved. The cost is that the history no longer
        records *that a poll happened* — `cron.log` is where you check liveness.

        Returns True if anything was written.
        """
        current = {r.item: (r.price_cents, r.quantity) for r in readings}
        if current and current == self.last_run_readings(target_id):
            return False
        return self.append(target_id, readings) > 0

    def min_price_cents(self, target_id: str) -> int | None:
        """Cheapest price ever recorded for this target, or None if no history."""
        prices = [r["price_cents"] for r in self.load(target_id) if r.get("price_cents") is not None]
        return min(prices) if prices else None

    def min_price_cents_since(self, target_id: str, cutoff: _dt.datetime) -> int | None:
        """Cheapest price standing at any point in [cutoff, now], or None if no history.

        ⚠️ The load-bearing subtlety is `append_if_changed`: this file is a **change
        log**, so a window can legitimately contain ZERO rows while the price was
        perfectly well defined throughout -- it simply never moved. A plain `min` over
        the rows inside the window would read that as "no data", when it actually means
        "no change". Those are opposites, and confusing them is the same shape of bug
        as collapsing `[]` into a broken adapter.

        So the last run recorded strictly BEFORE the cutoff is carried forward into the
        window: under change-log semantics that price was still standing when the
        window opened.

        ⭐ That carry-forward does a second job, and it is why this cannot be a naive
        window query. Without it a price that never moves would re-fire a window rule
        forever: the old low eventually slides out of the window, the remaining minimum
        rises, and the unchanged current price reads as a fresh "window low" on a market
        that did nothing. Carrying the standing price in keeps the rule edge-triggered,
        which is a project invariant, not a preference.
        """
        pool: list[int] = []
        before: list[tuple[_dt.datetime, int]] = []
        latest_before: _dt.datetime | None = None

        for r in self.load(target_id):
            price = r.get("price_cents")
            if price is None:
                continue
            ts = _dt.datetime.fromisoformat(r["captured_at"])
            if ts >= cutoff:
                pool.append(price)
            else:
                before.append((ts, price))
                if latest_before is None or ts > latest_before:
                    latest_before = ts

        if latest_before is not None:
            pool += [p for ts, p in before if ts == latest_before]
        return min(pool) if pool else None

    def last_run_min_cents(self, target_id: str) -> int | None:
        """Cheapest price in the most recent run (grouped by captured_at)."""
        rows = self.load(target_id)
        if not rows:
            return None
        last_ts = rows[-1]["captured_at"]
        prices = [r["price_cents"] for r in rows if r["captured_at"] == last_ts]
        return min(prices) if prices else None
