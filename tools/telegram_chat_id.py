#!/usr/bin/env python3
"""Find the chat id to put in TELEGRAM_CHAT_ID.

It is **your** chat id — the destination the bot sends to — not the bot's own id.
A Telegram bot cannot open a conversation; the chat has to have written to it first.

    1. In Telegram, open your bot and send it any message (e.g. /start).
    2. Run this script.
    3. Copy the id into .env as TELEGRAM_CHAT_ID.

Note: getUpdates only returns recent, unconsumed updates, and it will return nothing
at all if a webhook is set on the bot. Both cases are reported explicitly rather than
as an empty list, so "no output" never has to be interpreted.

⛔ This sets up YOU. To let a friend receive the same alerts, use
`tools/telegram_subscribers.py` — TELEGRAM_CHAT_ID holds exactly one chat.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pricewatch import config, telegram_api  # noqa: E402


def main() -> int:
    try:
        token = config.require("BOT_API_TOKEN", "Create a bot with @BotFather.")
    except KeyError as e:
        print(e, file=sys.stderr)
        return 2

    try:
        me = telegram_api.bot_identity(token)
    except telegram_api.TelegramApiError as e:
        print(f"getMe failed: {e}"
              f"{' — the token is not valid' if e.error_code == 401 else ''}", file=sys.stderr)
        return 1
    print(f"bot: @{me.get('username')} ({me.get('first_name')})")

    hook = telegram_api.webhook_url(token)
    if hook:
        print(f"\n⚠️  A webhook is set ({hook}). While a webhook exists, getUpdates "
              f"always returns empty — delete the webhook or read the id from your webhook logs.",
              file=sys.stderr)
        return 1

    seen = telegram_api.chats_seen(token)
    if not seen:
        print(f"\nNo chats found. Send @{me.get('username')} a message in Telegram "
              f"(any text, or /start), then run this again.\n"
              f"If you already did: getUpdates only returns RECENT updates, so send another one.",
              file=sys.stderr)
        return 1

    print("\nchat ids that have messaged this bot:")
    for cid, who in seen.items():
        print(f"  TELEGRAM_CHAT_ID={cid}    <- {who}")
    if len(seen) == 1:
        print("\nPut that line in .env")
    else:
        print("\nPut YOURS in .env. The others are candidates for "
              "`tools/telegram_subscribers.py --add`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
