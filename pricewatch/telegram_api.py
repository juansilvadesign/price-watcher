"""Thin Telegram Bot API client -- the one place that decodes Telegram's error envelope.

Two callers need this module and they need different things out of it:

* `notify.py` has to know whether a failure is **about that chat** (403 "bot was
  blocked by the user" -- stop trying, permanently) or merely **about the moment**
  (429, 5xx, a dropped connection -- try again next run). Getting that wrong in
  either direction is expensive: retry a blocked chat and every cron run warns
  forever; disable on a transient error and a subscriber is silently dropped.
* `tools/` has to name the reason `getUpdates` came back empty, instead of printing
  nothing and leaving "no output" to be interpreted.

Both answers live in the JSON body Telegram returns, **including on a 4xx** -- where
`urllib` raises `HTTPError` before the caller ever sees the body. Decoding it in one
place is what keeps `error_code` available to the sink that acts on it.

Zero dependencies, like the rest of the package: `urllib` and `json` only.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

TIMEOUT_S = 20
API_ROOT = "https://api.telegram.org"

#: Update keys that carry a chat. `my_chat_member` matters as much as `message`: it is
#: what arrives when someone presses Start or blocks the bot without typing anything.
_CHAT_BEARING_KEYS = ("message", "edited_message", "channel_post", "my_chat_member")


class TelegramApiError(RuntimeError):
    """Telegram answered, and the answer was a refusal.

    Carries Telegram's own `error_code` and `description` because the caller's decision
    depends on WHICH refusal it was. A bare "the request failed" collapses "this person
    blocked the bot" into "the network hiccuped", and those two want opposite responses.
    """

    def __init__(self, message: str, error_code: int | None = None,
                 description: str = "") -> None:
        super().__init__(message)
        self.error_code = error_code
        self.description = description


def method_url(token: str, method: str) -> str:
    return f"{API_ROOT}/bot{token}/{method}"


def _refusal(body: dict, where: str) -> TelegramApiError:
    code = body.get("error_code")
    desc = body.get("description") or ""
    return TelegramApiError(f"{where}: telegram refused ({code}) {desc}".strip(),
                            error_code=code, description=desc)


def request(url: str, params: dict | None = None, timeout: int = TIMEOUT_S) -> Any:
    """One API call. Returns the `result` field; raises `TelegramApiError` on refusal.

    Anything that is not a refusal -- DNS failure, timeout, connection reset -- is left
    to propagate as its own exception type. It carries no `error_code`, which is exactly
    how the caller tells "the network" apart from "this chat".
    """
    data = urllib.parse.urlencode(params).encode() if params else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            body = json.load(e)
        except Exception:                                # noqa: BLE001 -- body may be HTML
            raise TelegramApiError(f"HTTP {e.code} with no JSON body",
                                   error_code=e.code) from e
        raise _refusal(body, f"HTTP {e.code}") from e
    if not body.get("ok"):
        raise _refusal(body, "api")
    return body.get("result")


def call(token: str, method: str, params: dict | None = None) -> Any:
    return request(method_url(token, method), params)


# ------------------------------------------------------------------ tool-side helpers

def bot_identity(token: str) -> dict:
    """`{'username': ..., 'first_name': ...}`. Raises on a bad token."""
    return call(token, "getMe") or {}


def webhook_url(token: str) -> str | None:
    """The webhook set on the bot, if any.

    Worth its own call: while a webhook exists, `getUpdates` returns an empty list
    forever, which is indistinguishable from "nobody has messaged the bot" unless you
    ask. Every tool here reports it explicitly rather than printing an empty list.
    """
    return (call(token, "getWebhookInfo") or {}).get("url") or None


def chats_seen(token: str) -> dict[str, str]:
    """`{chat_id: 'who (type)'}` for every chat in the pending update queue.

    ⚠️ `getUpdates` returns only **recent, unconfirmed** updates (Telegram keeps them
    ~24h). An empty result means "nothing recent", never "nobody ever messaged you".
    Called without an `offset`, so it does not confirm/consume the queue: two tools can
    read it in any order without stealing each other's updates.

    Keys are strings -- chat ids are integers on the wire and strings everywhere in this
    project, and mixing the two makes an id compare unequal to itself.
    """
    seen: dict[str, str] = {}
    for update in call(token, "getUpdates") or []:
        for key in _CHAT_BEARING_KEYS:
            chat = (update.get(key) or {}).get("chat")
            if not chat:
                continue
            who = chat.get("username") or chat.get("title") or chat.get("first_name") or "?"
            seen[str(chat["id"])] = f"{who} ({chat.get('type')})"
    return seen
