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
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pricewatch import config  # noqa: E402


def api(token: str, method: str) -> dict:
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/{method}", timeout=20) as r:
        return json.load(r)


def main() -> int:
    try:
        token = config.require("BOT_API_TOKEN", "Create a bot with @BotFather.")
    except KeyError as e:
        print(e, file=sys.stderr)
        return 2

    try:
        me = api(token, "getMe")["result"]
    except urllib.error.HTTPError as e:
        print(f"getMe failed: HTTP {e.code}"
              f"{' — the token is not valid' if e.code == 401 else ''}", file=sys.stderr)
        return 1
    print(f"bot: @{me.get('username')} ({me.get('first_name')})")

    hook = api(token, "getWebhookInfo").get("result", {})
    if hook.get("url"):
        print(f"\n⚠️  A webhook is set ({hook['url']}). While a webhook exists, getUpdates "
              f"always returns empty — delete the webhook or read the id from your webhook logs.",
              file=sys.stderr)
        return 1

    updates = api(token, "getUpdates").get("result", [])
    seen: dict[int, str] = {}
    for u in updates:
        for key in ("message", "edited_message", "channel_post", "my_chat_member"):
            chat = (u.get(key) or {}).get("chat")
            if chat:
                who = chat.get("username") or chat.get("title") or chat.get("first_name") or "?"
                seen[chat["id"]] = f"{who} ({chat.get('type')})"

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
