#!/usr/bin/env python3
"""price-watcher CLI — run one pass over every enabled target.

    python3 watch.py                      # all enabled targets
    python3 watch.py --only rockinrio2026-09-04
    python3 watch.py --dry-run            # fetch + evaluate, write nothing
    python3 watch.py --list               # show the registry and exit

    python3 watch.py --notifier console telegram toast
    python3 watch.py --test-notify        # prove delivery works, no waiting

Exit codes: 0 = every target read cleanly · 1 = at least one adapter failed ·
2 = configuration error · 3 = alerts were computed but delivery failed. Distinct
codes matter under cron, where 3 is the one that means "you were not told".
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pricewatch import adapters, notify, rules
from pricewatch.filters import FilterError, apply_filters
from pricewatch.history import History
from pricewatch.models import AdapterError, Alert, Reading, fmt_brl, utcnow_iso
from pricewatch.notify import NotifyError
from pricewatch.registry import ConfigError, load_targets

ROOT = Path(__file__).resolve().parent


def run_target(target, history, notifier, dry_run: bool, verbose: bool) -> str:
    """Run one target. Returns "ok", "adapter" or "delivery"."""
    print(f"\n=== {target.label}  [{target.id}]")
    adapter = adapters.build(target.adapter)

    try:
        raw = adapter.fetch(target)
    except AdapterError as e:
        print(f"  ADAPTER FAILED: {e}", file=sys.stderr)
        return "adapter"

    readings = apply_filters(raw, target.filters, where=target.id)
    print(f"  {len(raw)} listings seen, {len(readings)} after filters")

    if not readings:
        print("  nothing on sale matching this target's filters (no alerts evaluated)")
        return "ok"

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
    elif history.append_if_changed(target.id, readings):
        print(f"  recorded {len(readings)} readings")
    else:
        print("  unchanged since the last recording — nothing written")

    if fired:
        try:
            notifier.send(target.label, fired)
        except NotifyError as e:
            print(f"  DELIVERY FAILED: {e}", file=sys.stderr)
            return "delivery"
    else:
        prior = history.min_price_cents(target.id)
        note = f"record low so far {fmt_brl(prior)}" if prior is not None else "baseline established"
        print(f"  no alerts ({note})")
    return "ok"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run one price-watch pass over all targets.")
    ap.add_argument("--targets", default=ROOT / "targets", type=Path)
    ap.add_argument("--history", default=ROOT / "history", type=Path)
    ap.add_argument("--only", nargs="*", metavar="ID", help="run only these target ids")
    ap.add_argument("--dry-run", action="store_true", help="fetch and evaluate, write nothing")
    ap.add_argument("--list", action="store_true", help="list targets and exit")
    ap.add_argument("--verbose", "-v", action="store_true", help="print every listing, not just the cheapest")
    ap.add_argument("--notifier", nargs="+", metavar="SINK", choices=sorted(notify.SINKS),
                    help="one or more sinks; overrides PRICEWATCH_NOTIFIERS (default: console)")
    ap.add_argument("--test-notify", action="store_true",
                    help="send one synthetic alert through the configured sinks and exit")
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

    names = notify.configured_names(args.notifier)
    try:
        notifier = notify.build(names, on_warning=lambda m: print(m, file=sys.stderr))
    except Exception as e:
        # Fail here, not on the first real alert days from now. A sink that cannot be
        # constructed is a misconfiguration, and discovering it at alert time means
        # the one message you cared about is the one that was lost.
        print(f"config error building notifier(s) {names}: {e}", file=sys.stderr)
        return 2
    print(f"notifiers: {', '.join(names)}")

    if args.test_notify:
        probe = Reading(target_id="test", site="test", item="TEST || probe",
                        price_cents=12345, currency="BRL", quantity=1,
                        captured_at=utcnow_iso(), source_url="https://example.test/probe")
        alert = Alert(target_id="test", rule="test_notify",
                      headline="TEST — R$ 123,45",
                      detail="Synthetic alert from `watch.py --test-notify`. "
                             "If you received this, delivery works.",
                      reading=probe)
        try:
            notifier.send("price-watcher delivery test", [alert])
        except NotifyError as e:
            print(f"DELIVERY FAILED: {e}", file=sys.stderr)
            return 3
        print("sent. Confirm it actually ARRIVED — a clean send is not a delivered message.")
        return 0

    history = History(args.history)
    enabled = [t for t in targets if t.enabled]
    if not enabled:
        print("no enabled targets", file=sys.stderr)
        return 2

    outcomes = []
    try:
        for t in enabled:
            outcomes.append(run_target(t, history, notifier, args.dry_run, args.verbose))
    except FilterError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2

    print()
    if "adapter" in outcomes:
        return 1
    if "delivery" in outcomes:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
