#!/usr/bin/env python3
"""price-watcher CLI — run one pass over every enabled target.

    python3 watch.py                      # all enabled targets
    python3 watch.py --only rockinrio2026-09-04
    python3 watch.py --dry-run            # fetch + evaluate, write nothing
    python3 watch.py --list               # show the registry and exit

Exit codes: 0 = every target read cleanly · 1 = at least one adapter failed
(so cron/`&&` chains notice) · 2 = configuration error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pricewatch import adapters, notify, rules
from pricewatch.filters import FilterError, apply_filters
from pricewatch.history import History
from pricewatch.models import AdapterError, fmt_brl
from pricewatch.registry import ConfigError, load_targets

ROOT = Path(__file__).resolve().parent


def run_target(target, history, notifier, dry_run: bool, verbose: bool) -> bool:
    """Run one target. Returns True on a clean read."""
    print(f"\n=== {target.label}  [{target.id}]")
    adapter = adapters.build(target.adapter)

    try:
        raw = adapter.fetch(target)
    except AdapterError as e:
        print(f"  ADAPTER FAILED: {e}", file=sys.stderr)
        return False

    readings = apply_filters(raw, target.filters, where=target.id)
    print(f"  {len(raw)} listings seen, {len(readings)} after filters")

    if not readings:
        print("  nothing on sale matching this target's filters (no alerts evaluated)")
        return True

    if verbose:
        for r in sorted(readings, key=lambda r: r.price_cents):
            print(f"    {r}")
    else:
        cheapest = min(readings, key=lambda r: r.price_cents)
        print(f"    cheapest: {cheapest}")

    # Rules MUST be evaluated before this run is appended, or every run becomes its
    # own baseline and nothing can ever fire.
    fired = rules.evaluate(target, readings, history)

    if dry_run:
        print(f"  [dry-run] {len(readings)} readings NOT written")
    else:
        history.append(target.id, readings)

    if fired:
        notifier.send(target.label, fired)
    else:
        prior = history.min_price_cents(target.id)
        note = f"record low so far {fmt_brl(prior)}" if prior is not None else "baseline established"
        print(f"  no alerts ({note})")
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run one price-watch pass over all targets.")
    ap.add_argument("--targets", default=ROOT / "targets", type=Path)
    ap.add_argument("--history", default=ROOT / "history", type=Path)
    ap.add_argument("--only", nargs="*", metavar="ID", help="run only these target ids")
    ap.add_argument("--dry-run", action="store_true", help="fetch and evaluate, write nothing")
    ap.add_argument("--list", action="store_true", help="list targets and exit")
    ap.add_argument("--verbose", "-v", action="store_true", help="print every listing, not just the cheapest")
    ap.add_argument("--notifier", default="console", choices=sorted(notify.SINKS))
    args = ap.parse_args(argv)

    try:
        targets = load_targets(args.targets, only=args.only)
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2

    if args.list:
        for t in targets:
            state = "on " if t.enabled else "off"
            active = [n for n, c in t.rules.items() if c.get("enabled")]
            print(f"  [{state}] {t.id:<28} {t.adapter:<18} rules={','.join(active) or '-'}  {t.label}")
        return 0

    history = History(args.history)
    notifier = notify.build(args.notifier)
    enabled = [t for t in targets if t.enabled]
    if not enabled:
        print("no enabled targets", file=sys.stderr)
        return 2

    ok = True
    try:
        for t in enabled:
            ok &= run_target(t, history, notifier, args.dry_run, args.verbose)
    except FilterError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2

    print()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
