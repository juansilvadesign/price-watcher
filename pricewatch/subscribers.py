"""The Telegram recipient list: you, plus the friends you approved.

`TELEGRAM_CHAT_ID` in `.env` stays exactly what it always was -- **your** chat, the one
that must never silently stop being alerted. This file is purely additive: everybody in
it receives the same alerts you do, from the same run.

⭐ **Two states that look alike and are not:**

* **File absent** -> nobody is subscribed. Valid, silent, and the state every install
  starts in. Delivery is owner-only, byte-identical to the behaviour before this module
  existed.
* **File present but unreadable** -> we do not know *who* the recipients are, which is
  not the same as knowing there are none. Raises `SubscriberError`.

That is this project's `AdapterError`-vs-`[]` invariant one layer up: an absent list is
data, a corrupt list is blindness. Collapsing them would let a typo'd file read as "no
friends are subscribed" for as long as it took someone to notice they had stopped
receiving alerts -- which is never, because *not receiving them* is what that looks
like from the outside.

Every validation here refuses rather than defaults, for the same reason `registry.py`
does: an entry that loads but can never receive is worse than one that fails loudly.
`lang` is the newest instance of that rule and the least obvious -- see `_lang`.

⛔ `subscribers.json` is gitignored. Chat ids are other people's personal data, and this
repo may be published -- there is nothing in this file that belongs in a commit.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from dataclasses import dataclass
from pathlib import Path

from . import config
from .messages import DEFAULT_LANG, LANGS

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "subscribers.json"


class SubscriberError(ValueError):
    """The subscriber file exists and cannot be trusted. Never downgraded to a warning."""


@dataclass(frozen=True)
class Subscriber:
    name: str
    chat_id: str
    enabled: bool = True
    #: The language THIS person's alerts are written in. Yours is not stored here:
    #: `TELEGRAM_CHAT_ID` is not a subscriber, and the owner reads `DEFAULT_LANG`.
    lang: str = DEFAULT_LANG
    added_at: str = ""
    disabled_reason: str = ""

    def to_json(self) -> dict:
        # `lang` is written even at its default, unlike `added_at`. It is a setting you
        # are meant to find and edit by hand, and a key that only appears once somebody
        # has already changed it is a key nobody discovers.
        d = {"name": self.name, "chat_id": self.chat_id, "enabled": self.enabled,
             "lang": self.lang}
        if self.added_at:
            d["added_at"] = self.added_at
        # Written only when set: a healthy entry stays clean, and the presence of the
        # key is itself the record that this subscriber was disabled by the notifier
        # rather than by hand.
        if self.disabled_reason:
            d["disabled_reason"] = self.disabled_reason
        return d


def _chat_id_str(raw, where: str) -> str:
    """Accept the int form Telegram uses on the wire; refuse everything else.

    `isinstance(True, int)` is True, so a bare `true` would become the chat id "1" --
    an entry that loads clean, addresses a chat that is not yours, and quietly never
    delivers. Same trap `registry.py` guards on `price_brl`, one type earlier.
    """
    if isinstance(raw, bool) or raw is None:
        raise SubscriberError(f"{where}: chat_id must be a string or integer, got {raw!r}")
    if isinstance(raw, int):
        return str(raw)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    raise SubscriberError(f"{where}: chat_id must be a non-empty string or integer, got {raw!r}")


def _lang(raw: dict, where: str) -> str:
    """The language for one entry. Absent is a default; wrong is a refusal.

    Absent means "nobody chose", and English is what this tool has always sent -- the
    same shape as an absent `subscribers.json` meaning nobody is subscribed.

    An unknown value is refused instead of falling back, and the reason is that the
    fallback is *invisible to the only person who would notice it*. A friend approved
    with `"pt_br"` would receive perfectly working English alerts forever; you would see
    an entry that looks configured, and they would never think to mention that the
    thing you set up for them arrived in the wrong language. Same failure shape as a
    rule enabled without its parameter: configured, plausible, silently not what was
    asked for. The cost is stated and accepted -- a typo here drops the whole Telegram
    sink for the run (`build()` degrades, the other sinks survive) until you fix it.
    """
    if "lang" not in raw:
        return DEFAULT_LANG
    lang = raw["lang"]
    if not isinstance(lang, str) or lang not in LANGS:
        raise SubscriberError(
            f"{where}: 'lang' must be one of {', '.join(LANGS)} — got {lang!r}. "
            f"Fix it by hand or with `--set-lang <chat_id> --lang <one of those>`.")
    return lang


def _subscriber_from(raw, where: str) -> Subscriber:
    if not isinstance(raw, dict):
        raise SubscriberError(f"{where}: each subscriber must be an object, got {type(raw).__name__}")
    if "chat_id" not in raw:
        raise SubscriberError(f"{where}: missing required key 'chat_id'")

    chat_id = _chat_id_str(raw["chat_id"], where)

    enabled = raw.get("enabled", True)
    # A string "false" is truthy, so `bool()` here would arm an entry its author
    # believed was off. Refuse instead of guessing which they meant.
    if not isinstance(enabled, bool):
        raise SubscriberError(
            f"{where}: 'enabled' must be true or false, got {enabled!r}. "
            f"A quoted \"false\" is truthy and would deliver to a chat you switched off.")

    return Subscriber(
        name=str(raw.get("name") or f"chat:{chat_id}"),
        chat_id=chat_id,
        enabled=enabled,
        lang=_lang(raw, where),
        added_at=str(raw.get("added_at") or ""),
        disabled_reason=str(raw.get("disabled_reason") or ""),
    )


def parse(text: str, where: str) -> list[Subscriber]:
    """Parse the file body. Exposed so a test can drive it without touching a disk."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as e:
        raise SubscriberError(f"{where}: invalid JSON -- {e}") from e
    if not isinstance(raw, dict) or not isinstance(raw.get("subscribers"), list):
        raise SubscriberError(
            f"{where}: expected an object with a 'subscribers' array, got {type(raw).__name__}")

    subs = [_subscriber_from(r, f"{where}[{i}]") for i, r in enumerate(raw["subscribers"])]

    # A duplicate is not cosmetic: the same chat gets every alert twice, and
    # `set_enabled` would fix only the first of the two rows.
    seen: dict[str, int] = {}
    for i, s in enumerate(subs):
        if s.chat_id in seen:
            raise SubscriberError(
                f"{where}: chat_id {s.chat_id} appears twice (entries {seen[s.chat_id]} and {i})")
        seen[s.chat_id] = i
    return subs


class Store:
    """Read/write access to `subscribers.json`.

    Point it somewhere else with `PRICEWATCH_SUBSCRIBERS` (real env or `.env`), the same
    way `PRICEWATCH_NOTIFIERS` works.
    """

    def __init__(self, path: Path | str | None = None) -> None:
        if path is None:
            path = config.get("PRICEWATCH_SUBSCRIBERS") or DEFAULT_PATH
        self.path = Path(path)

    def load(self) -> list[Subscriber]:
        if not self.path.exists():
            return []
        return parse(self.path.read_text(encoding="utf-8"), self.path.name)

    def enabled(self) -> list[Subscriber]:
        return [s for s in self.load() if s.enabled]

    def save(self, subs: list[Subscriber]) -> None:
        """Write via a temp file + `os.replace`, so an interrupted write cannot leave a
        truncated list behind -- which `load()` would then refuse, taking the whole
        Telegram sink down with it."""
        payload = json.dumps({"subscribers": [s.to_json() for s in subs]},
                             indent=2, ensure_ascii=False) + "\n"
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, self.path)

    # ------------------------------------------------------------------ mutations

    def set_enabled(self, chat_id: str, enabled: bool, reason: str = "") -> bool:
        """Flip one subscriber. Returns whether anything actually changed.

        ⛔ Re-reads from disk before writing, deliberately. Two crontab lines fire in the
        same minute here (`* * * * *` and `*/5 * * * *`), so two runs hold this file at
        once. Writing back the snapshot *this* process loaded at startup would silently
        revert whatever the other one just wrote. This is not atomic against a true
        race -- it narrows the window to the microseconds between read and replace, and
        it preserves every entry this call did not touch.
        """
        subs = self.load()
        out, changed = [], False
        for s in subs:
            if s.chat_id == str(chat_id) and (s.enabled != enabled or
                                              (not enabled and s.disabled_reason != reason)):
                out.append(Subscriber(name=s.name, chat_id=s.chat_id, enabled=enabled,
                                      lang=s.lang, added_at=s.added_at,
                                      disabled_reason=reason if not enabled else ""))
                changed = True
            else:
                out.append(s)
        if changed:
            self.save(out)
        return changed

    def disable(self, chat_id: str, reason: str) -> bool:
        return self.set_enabled(chat_id, False, reason)

    def set_lang(self, chat_id: str, lang: str) -> bool:
        """Change one subscriber's language. Returns whether anything changed.

        Re-reads from disk before writing for the same reason `set_enabled` does: two
        cron cadences hold this file at once, and one of them auto-disables people.
        """
        if lang not in LANGS:
            raise SubscriberError(
                f"lang must be one of {', '.join(LANGS)} — got {lang!r}")
        subs = self.load()
        out, changed = [], False
        for s in subs:
            if s.chat_id == str(chat_id) and s.lang != lang:
                out.append(Subscriber(name=s.name, chat_id=s.chat_id, enabled=s.enabled,
                                      lang=lang, added_at=s.added_at,
                                      disabled_reason=s.disabled_reason))
                changed = True
            else:
                out.append(s)
        if changed:
            self.save(out)
        return changed

    def add(self, chat_id: str, name: str = "", lang: str = DEFAULT_LANG) -> Subscriber:
        """Append one subscriber. Raises if the chat id is already present."""
        chat_id = _chat_id_str(chat_id, "add")
        # Checked before the duplicate check so a bad language never half-succeeds, and
        # refused rather than defaulted for the reason `_lang` gives.
        if lang not in LANGS:
            raise SubscriberError(
                f"lang must be one of {', '.join(LANGS)} — got {lang!r}")
        subs = self.load()
        if any(s.chat_id == chat_id for s in subs):
            raise SubscriberError(f"chat_id {chat_id} is already in {self.path.name}")
        sub = Subscriber(name=name or f"chat:{chat_id}", chat_id=chat_id, enabled=True,
                         lang=lang,
                         added_at=_dt.datetime.now(_dt.timezone.utc)
                         .replace(microsecond=0).isoformat())
        self.save(subs + [sub])
        return sub

    def remove(self, chat_id: str) -> bool:
        subs = self.load()
        kept = [s for s in subs if s.chat_id != str(chat_id)]
        if len(kept) == len(subs):
            return False
        self.save(kept)
        return True
