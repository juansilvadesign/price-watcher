#!/usr/bin/env python3
"""Manage who receives the alerts besides you.

The bot is **public** — anyone who finds it can message it — so being able to reach the
bot is not the same as being on the list. This tool is the gate: a friend opens your bot
link and sends anything, and you approve the ones you actually know, by name.

    # 1. friend messages the bot (any text, or /start)
    python3 tools/telegram_subscribers.py --pending          # who is waiting
    python3 tools/telegram_subscribers.py --add 1122334455 --name rafa --lang pt-BR
    python3 tools/telegram_subscribers.py --test 1122334455  # prove it reaches them
    python3 tools/telegram_subscribers.py                    # the current list

    python3 tools/telegram_subscribers.py --set-lang 1122334455 --lang pt-BR
    python3 tools/telegram_subscribers.py --disable 1122334455 --reason "asked to pause"
    python3 tools/telegram_subscribers.py --remove  1122334455

⭐ `--lang` is the language THEIR alerts are written in (en-US, pt-BR; default en-US).
Yours never changes — you are not on this list, and console and toast stay English.
`--test` sends in the language that chat is already approved with, so it checks the
setting and the delivery in one go.

⚠️ `--pending` reads `getUpdates`, which only returns **recent** updates (Telegram keeps
them ~24h) and returns nothing at all while a webhook is set. Both are reported by name
rather than as an empty list, because "nobody messaged me" and "I cannot see who did"
are different problems with the same appearance.

⛔ Everyone on this list receives **every** alert for **every** target, exactly as you do
— the language is the only thing that is per-person. There is no per-person filtering of
*which* targets or rules reach whom; if you need one, that is a feature to build, not a
setting to find.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pricewatch import config, subscribers, telegram_api  # noqa: E402
from pricewatch.messages import DEFAULT_LANG, LANGS  # noqa: E402
from pricewatch.models import Alert, Reading, utcnow_iso  # noqa: E402
from pricewatch.notify import NotifyError, TelegramNotifier  # noqa: E402


def _token() -> str:
    return config.require("BOT_API_TOKEN", "Create a bot with @BotFather.")


def _owner() -> str | None:
    return config.get("TELEGRAM_CHAT_ID")


def cmd_list(store: subscribers.Store) -> int:
    subs = store.load()
    owner = _owner()
    print(f"owner (TELEGRAM_CHAT_ID): {owner or '(not set)'}")
    print(f"{store.path.name}: {len(subs)} subscriber(s)"
          f"{'' if store.path.exists() else '  (file does not exist yet — nobody is subscribed)'}")
    for s in subs:
        state = "on " if s.enabled else "off"
        why = f"   {s.disabled_reason}" if s.disabled_reason else ""
        print(f"  [{state}] {s.name:<20} {s.chat_id:<16} {s.lang:<6} "
              f"added {s.added_at or '?'}{why}")
    return 0


def cmd_pending(store: subscribers.Store) -> int:
    token = _token()
    me = telegram_api.bot_identity(token)
    print(f"bot: @{me.get('username')} ({me.get('first_name')})")

    hook = telegram_api.webhook_url(token)
    if hook:
        print(f"\n⚠️  A webhook is set ({hook}). While one exists, getUpdates always returns "
              f"empty — delete the webhook or read chat ids from your webhook logs.",
              file=sys.stderr)
        return 1

    seen = telegram_api.chats_seen(token)
    known = {s.chat_id for s in store.load()}
    owner = _owner()
    pending = {cid: who for cid, who in seen.items() if cid not in known and cid != owner}
    filtered = len(seen) - len(pending)

    if not pending:
        print(f"\nNo pending chats"
              f"{f' ({filtered} already known)' if filtered else ''}. "
              f"Ask them to send @{me.get('username')} a message, then run this again.\n"
              f"⚠️ getUpdates only returns RECENT updates — if they messaged days ago, "
              f"have them send another one.", file=sys.stderr)
        return 1

    print(f"\npending chats that messaged the bot"
          f"{f' ({filtered} already known, hidden)' if filtered else ''}:")
    for cid, who in pending.items():
        print(f"  {cid:<16} {who}")
    example = next(iter(pending))
    # `--lang` is shown here because this is the screen you are on when you decide to
    # approve somebody, and it is the last moment it costs nothing to get right.
    print(f"\nAdd one with:\n"
          f"  python3 tools/telegram_subscribers.py --add {example} --name <who> "
          f"[--lang {'|'.join(LANGS)}]")
    return 0


def cmd_add(store: subscribers.Store, chat_id: str, name: str | None, lang: str) -> int:
    owner = _owner()
    if owner and str(chat_id) == str(owner):
        # Not a duplicate to be deduped later: that id is already the critical recipient.
        # Adding it would demote your own delivery failures to best-effort warnings on
        # the second copy, and send you every alert twice in the meantime.
        print(f"{chat_id} is your own TELEGRAM_CHAT_ID — you already receive everything. "
              f"The subscriber list is for other people.", file=sys.stderr)
        return 2

    if not name:
        # Best-effort courtesy only: a name makes `--list` and the per-run fan-out line
        # readable. Never fatal -- adding somebody must work with no network and with an
        # update queue that has already aged out.
        try:
            name = telegram_api.chats_seen(_token()).get(str(chat_id), "").split(" (")[0] or None
        except Exception as e:                          # noqa: BLE001
            print(f"(could not look up a name: {type(e).__name__}: {e})", file=sys.stderr)

    try:
        sub = store.add(chat_id, name or "", lang)
    except subscribers.SubscriberError as e:
        print(e, file=sys.stderr)
        return 2
    print(f"added: {sub.name} ({sub.chat_id}) in {sub.lang} — receives every alert "
          f"for every target")
    print(f"Prove it reaches them, in that language:\n"
          f"  python3 tools/telegram_subscribers.py --test {sub.chat_id}")
    return 0


def cmd_set_lang(store: subscribers.Store, chat_id: str, lang: str | None) -> int:
    if not lang:
        print(f"--set-lang needs --lang; one of {', '.join(LANGS)}", file=sys.stderr)
        return 2
    if not any(s.chat_id == str(chat_id) for s in store.load()):
        print(f"{chat_id} is not in {store.path.name}", file=sys.stderr)
        return 1
    changed = store.set_lang(chat_id, lang)
    print(f"{chat_id} now receives {lang}{'' if changed else ' (already did)'}")
    print(f"Confirm it reads right to them:\n"
          f"  python3 tools/telegram_subscribers.py --test {chat_id}")
    return 0


def cmd_remove(store: subscribers.Store, chat_id: str) -> int:
    if not store.remove(chat_id):
        print(f"{chat_id} is not in {store.path.name}", file=sys.stderr)
        return 1
    print(f"removed {chat_id}")
    return 0


def cmd_set_enabled(store: subscribers.Store, chat_id: str, enabled: bool, reason: str) -> int:
    if not any(s.chat_id == str(chat_id) for s in store.load()):
        print(f"{chat_id} is not in {store.path.name}", file=sys.stderr)
        return 1
    changed = store.set_enabled(chat_id, enabled, reason)
    print(f"{chat_id} is now {'enabled' if enabled else 'disabled'}"
          f"{'' if changed else ' (already was)'}")
    return 0


def cmd_test(store: subscribers.Store, chat_id: str, lang: str | None) -> int:
    """Send one synthetic alert to ONE chat, through the real notifier.

    ⚠️ `watch.py --test-notify` fans out to everybody — right for testing the fan-out,
    wrong for checking a friend you just added. This path addresses the given chat as the
    notifier's *owner* slot, so it exercises the real formatting and escaping and a
    failure is loud rather than a warning.

    The language comes from the LIST, not from `DEFAULT_LANG`, because the owner slot is
    English and this command exists to check the friend you just approved. Sending them
    English here would report success on a setting it never exercised — the one thing you
    cannot catch afterwards, since your own copy of every alert is English regardless.
    `--lang` overrides, for a chat that is not on the list yet.
    """
    known = {s.chat_id: s for s in store.load()}
    lang = lang or (known[str(chat_id)].lang if str(chat_id) in known else DEFAULT_LANG)

    probe = Reading(target_id="test", site="test", item="TEST || probe", price_cents=12345,
                    currency="BRL", quantity=1, captured_at=utcnow_iso(),
                    source_url="https://example.test/probe")
    alert = Alert(target_id="test", rule="test_notify", message_key="test_notify",
                  params={"price": probe.price_cents}, reading=probe)
    # An absent file is the documented "nobody is subscribed" state, so an empty temp dir
    # is exactly a store with no subscribers -- no test double, no second code path.
    with tempfile.TemporaryDirectory() as d:
        notifier = TelegramNotifier(chat_id=str(chat_id), owner_lang=lang,
                                    store=subscribers.Store(Path(d) / "none.json"))
        try:
            notifier.send("price-watcher delivery test", [alert])
        except NotifyError as e:
            print(f"DELIVERY FAILED: {e}", file=sys.stderr)
            return 3
    print(f"sent to {chat_id} in {lang}. Confirm it ARRIVED and READS RIGHT — a clean "
          f"send is not a delivered message.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Manage the Telegram subscriber list (subscribers.json).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Everyone on the list receives every alert, exactly as you do.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--list", action="store_true", help="show the list (default)")
    g.add_argument("--pending", action="store_true",
                   help="chats that messaged the bot and are not on the list")
    g.add_argument("--add", metavar="CHAT_ID", help="approve a chat")
    g.add_argument("--remove", metavar="CHAT_ID", help="drop a chat entirely")
    g.add_argument("--enable", metavar="CHAT_ID", help="re-enable a disabled chat")
    g.add_argument("--disable", metavar="CHAT_ID", help="stop sending, keep the entry")
    g.add_argument("--set-lang", metavar="CHAT_ID", help="change a chat's language (with --lang)")
    g.add_argument("--test", metavar="CHAT_ID", help="send one synthetic alert to this chat only")
    ap.add_argument("--name", help="how this person appears in --list and in each run's header")
    ap.add_argument("--lang", choices=LANGS, default=None,
                    help=f"language THEIR alerts are written in (default: {DEFAULT_LANG}). "
                         f"Yours never changes.")
    ap.add_argument("--reason", default="disabled by hand", help="recorded with --disable")
    ap.add_argument("--file", type=Path, default=None,
                    help="subscriber file (default: subscribers.json beside watch.py)")
    args = ap.parse_args(argv)

    store = subscribers.Store(args.file)
    try:
        if args.pending:
            return cmd_pending(store)
        if args.add:
            return cmd_add(store, args.add, args.name, args.lang or DEFAULT_LANG)
        if args.set_lang:
            return cmd_set_lang(store, args.set_lang, args.lang)
        if args.remove:
            return cmd_remove(store, args.remove)
        if args.enable:
            return cmd_set_enabled(store, args.enable, True, "")
        if args.disable:
            return cmd_set_enabled(store, args.disable, False, args.reason)
        if args.test:
            return cmd_test(store, args.test, args.lang)
        return cmd_list(store)
    except subscribers.SubscriberError as e:
        # The list exists and cannot be trusted. Refusing here is the point: silently
        # treating it as empty is the failure this whole file is built to avoid.
        print(f"subscriber file error: {e}", file=sys.stderr)
        return 2
    except KeyError as e:
        print(e, file=sys.stderr)
        return 2
    except telegram_api.TelegramApiError as e:
        print(f"telegram: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
