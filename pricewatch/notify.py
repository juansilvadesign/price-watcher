"""Notification sinks.

Three sinks ship: `console`, `telegram`, `toast` (Windows, via WSL). Select any
combination — `--notifier console telegram toast`, or set `PRICEWATCH_NOTIFIERS`
in `.env` so a cron line stays short.

The `telegram` sink fans out: to **you** (`TELEGRAM_CHAT_ID`, critical) and to every
friend you approved into `subscribers.json` (best-effort). See `subscribers.py` for why
those two tiers are not symmetric.

Two rules the harness depends on:

* **Every sink is attempted, even after one fails.** A Telegram outage must not
  cost you the toast that would have reached you anyway. The same rule applies one
  layer down, across Telegram recipients: a friend who blocked the bot must not cost
  you your own message.
* **A delivery failure is never swallowed.** It raises `NotifyError` after all
  sinks have been tried, and `watch.py` turns that into a distinct exit code. A
  notifier that fails quietly is worse than having no notifier: it converts "you
  were not alerted" into "there was nothing to alert about".

Both network and subprocess sinks take an injectable transport so the whole module
is testable with no network and no Windows.
"""

from __future__ import annotations

import base64
import html
import os
import shutil
import subprocess
import sys
import xml.sax.saxutils as _xml
from typing import Callable, Protocol

from . import config, subscribers, telegram_api
from .models import Alert, utcnow_iso


class NotifyError(RuntimeError):
    """One or more sinks failed to deliver. Never raised before all were tried."""


class Notifier(Protocol):
    name: str

    def send(self, target_label: str, alerts: list[Alert]) -> None: ...


# --------------------------------------------------------------------------- console

class ConsoleNotifier:
    name = "console"

    def send(self, target_label: str, alerts: list[Alert]) -> None:
        for a in alerts:
            print(f"  !! [{a.rule}] {a.headline}")
            print(f"     {a.detail}")
            print(f"     {a.reading.source_url}")


# -------------------------------------------------------------------------- telegram

def _urllib_post(url: str, payload: dict) -> None:
    telegram_api.request(url, payload)


def is_permanent_chat_failure(err: BaseException) -> bool:
    """Is this refusal about the CHAT, and still true next run?

    Only a yes may cost a subscriber their place on the list. Everything else -- 429
    rate limits, 5xx, a dropped connection -- is about the moment, carries no
    `error_code` or the wrong one, and must be retried.

    ⚠️ The 400 leg is narrowed to "chat not found" **on purpose**. `parse_mode=HTML`
    failures ("can\'t parse entities") are also 400, and unlike a blocked chat they hit
    every recipient at once: treating any 400 as permanent would let one ticket name the
    formatter mishandles disable the entire subscriber list in a single run, silently.
    """
    code = getattr(err, "error_code", None)
    desc = (getattr(err, "description", "") or "").lower()
    if code == 403:                     # blocked by the user, kicked, or deactivated
        return True
    return code == 400 and "chat not found" in desc


class TelegramNotifier:
    """Sends to YOU, and to every friend you have approved.

    A bot cannot open a conversation, so every recipient — you included — has to have
    messaged it first. That is what `tools/telegram_chat_id.py` (you) and
    `tools/telegram_subscribers.py` (everyone else) exist for.

    ⭐ **Two tiers, deliberately asymmetric:**

    * The **owner** chat (`TELEGRAM_CHAT_ID`) is critical. A failure there raises
      `NotifyError`, which `watch.py` turns into exit **3** — the code that means *you*
      were not told.
    * A **subscriber** is best-effort. Their failure warns and leaves the exit code
      alone, and a *permanent* refusal disables them in `subscribers.json` rather than
      being retried forever. A friend who blocks the bot must not make every cron run
      exit 3: that would destroy exit 3 as a signal about **you**, which is the only
      thing it is for.

    Every recipient is attempted before anything is raised — the same rule
    `MultiNotifier` applies across sinks, one layer down.

    The recipient list is read at **construction**, not at send time, so a corrupt
    `subscribers.json` is a startup failure exactly like a missing chat id, and never a
    discovery made on the one alert that mattered.
    """

    name = "telegram"

    def __init__(self, token: str | None = None, chat_id: str | None = None,
                 post: Callable[[str, dict], None] = _urllib_post,
                 store: "subscribers.Store | None" = None,
                 on_warning: Callable[[str], None] | None = None) -> None:
        self.token = token or config.require(
            "BOT_API_TOKEN", "Create a bot with @BotFather to get one.")
        self.chat_id = chat_id or config.require(
            "TELEGRAM_CHAT_ID",
            "This is YOUR chat id, not the bot's. Message the bot once, then run "
            "`python3 tools/telegram_chat_id.py`.")
        # A list here would be sent verbatim as one chat id, and Telegram would answer
        # 400 "chat not found" on every run — a working setup that delivers to nobody.
        # Say where friends actually go instead of failing cryptically.
        if "," in self.chat_id:
            raise NotifyError(
                f"TELEGRAM_CHAT_ID={self.chat_id!r} looks like a list, but it names exactly "
                f"ONE chat: yours. Friends live in subscribers.json — add them with "
                f"`python3 tools/telegram_subscribers.py --add <chat_id> --name <who>`.")
        self._post = post
        self._warn = on_warning or (lambda m: print(m, file=sys.stderr))
        self.store = subscribers.Store() if store is None else store
        # Deduped against the owner: an id that is both yours and a subscriber's would
        # deliver every alert to you twice. The tool refuses to add it; this is the
        # backstop for a hand-edited file.
        self.subscribers = [s for s in self.store.enabled() if s.chat_id != self.chat_id]

    @property
    def recipients(self) -> list[str]:
        """Owner first, then subscribers — the order messages are actually sent in."""
        return [self.chat_id] + [s.chat_id for s in self.subscribers]

    def format(self, target_label: str, alerts: list[Alert]) -> str:
        """HTML for Telegram. Every interpolated value is escaped — ticket-class
        names come from a third-party page and must never be trusted as markup."""
        e = html.escape
        lines = [f"<b>{e(target_label)}</b>"]
        for a in alerts:
            lines.append(f"\n⚠️ <b>{e(a.headline)}</b>\n{e(a.detail)}")
        lines.append(f"\n{e(alerts[0].reading.source_url)}")
        return "\n".join(lines)

    def send(self, target_label: str, alerts: list[Alert]) -> None:
        if not alerts:
            return
        text = self.format(target_label, alerts)

        owner_error = None
        try:
            self._deliver(self.chat_id, text)
        except Exception as e:                          # noqa: BLE001 -- re-raised below
            owner_error = f"{type(e).__name__}: {e}"

        # Attempted even when the owner send just failed. The two failures are usually
        # unrelated — a blocked chat is about one chat — and a friend's message that
        # would have gone through should not be lost to yours not going through.
        for sub in self.subscribers:
            try:
                self._deliver(sub.chat_id, text)
            except Exception as e:                      # noqa: BLE001 -- warn, never raise
                self._subscriber_failed(sub, e)

        if owner_error:
            raise NotifyError(f"telegram owner chat {self.chat_id} — {owner_error}")

    def _deliver(self, chat_id: str, text: str) -> None:
        self._post(
            telegram_api.method_url(self.token, "sendMessage"),
            {"chat_id": chat_id,
             "text": text,
             "parse_mode": "HTML",
             "disable_web_page_preview": "true"},
        )

    def _subscriber_failed(self, sub: "subscribers.Subscriber", err: Exception) -> None:
        permanent = is_permanent_chat_failure(err)
        self._warn(
            f"WARNING: telegram subscriber {sub.name} ({sub.chat_id}) not reached — "
            f"{type(err).__name__}: {err}"
            + (f"; disabling in {self.store.path.name}" if permanent
               else "; will retry next run"))
        if not permanent:
            return
        try:
            self.store.disable(sub.chat_id, f"{err} [{utcnow_iso()}]")
        except Exception as e:                          # noqa: BLE001
            # Bookkeeping, not delivery. Everyone reachable was still reached; failing
            # to RECORD that one person was not is not a reason to report the alert as
            # undelivered. It costs a repeated warning next run, nothing more.
            self._warn(f"WARNING: could not disable {sub.chat_id} in "
                       f"{self.store.path.name}: {type(e).__name__}: {e}")


# ----------------------------------------------------------------------- windows toast

def _powershell_run(argv: list[str]) -> None:
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise NotifyError(f"powershell exited {proc.returncode}: {(proc.stderr or '').strip()[:300]}")


class WindowsToastNotifier:
    """Native Windows toast from WSL, with no module to install.

    Uses the WinRT `ToastNotificationManager` under the built-in Windows PowerShell
    AppId, driven through `-EncodedCommand` so no quoting survives the WSL/Windows
    boundary to be mangled.

    ⚠️ **A successful call is not a visible toast.** `Show()` returns without error
    even when Focus Assist / Do Not Disturb suppresses the banner, or when
    notifications are off for the host app. This sink can only report that Windows
    accepted it — treat it as best-effort and never as the only channel.
    """

    name = "toast"
    APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"

    #: Fallbacks for when PATH does not carry WSL's Windows interop entries. Under
    #: cron, PATH is roughly /usr/bin:/bin and `which powershell.exe` returns None --
    #: which, before this existed, aborted the entire run at startup and cost the
    #: prices and the Telegram alert along with the toast.
    CANDIDATES = (
        "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
        "/mnt/c/WINDOWS/System32/WindowsPowerShell/v1.0/powershell.exe",
    )

    @classmethod
    def find_powershell(cls) -> str | None:
        found = shutil.which("powershell.exe")
        if found:
            return found
        for c in cls.CANDIDATES:
            if os.path.exists(c):
                return c
        return None

    def __init__(self, runner: Callable[[list[str]], None] = _powershell_run,
                 powershell: str | None = None) -> None:
        self._run = runner
        self._ps = powershell or self.find_powershell()
        if not self._ps:
            raise NotifyError(
                "powershell.exe not found on PATH nor at any known Windows location — "
                "the 'toast' sink only works from WSL on a Windows host. Drop it from "
                "--notifier / PRICEWATCH_NOTIFIERS.")

    #: Apostrophe and quote are escaped as XML entities on purpose, not for XML's
    #: sake but for PowerShell's: the toast XML is embedded in a single-quoted PS
    #: string, so one `'` in a ticket-class name would terminate that string early
    #: and the whole notification would die with a parse error at the worst moment.
    _ESC = {"'": "&apos;", '"': "&quot;"}

    def build_script(self, title: str, body: str) -> str:
        t = _xml.escape(title, self._ESC)
        b = _xml.escape(body, self._ESC)
        return (
            "$ErrorActionPreference='Stop'\n"
            "[void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime]\n"
            "[void][Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType=WindowsRuntime]\n"
            f"$AppId = '{self.APP_ID}'\n"
            "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument\n"
            "$xml.LoadXml('<toast><visual><binding template=\"ToastGeneric\">"
            f"<text>{t}</text><text>{b}</text>"
            "</binding></visual></toast>')\n"
            "$toast = New-Object Windows.UI.Notifications.ToastNotification $xml\n"
            "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($AppId).Show($toast)\n"
        )

    def send(self, target_label: str, alerts: list[Alert]) -> None:
        if not alerts:
            return
        headlines = " · ".join(a.headline for a in alerts)
        script = self.build_script(target_label, headlines)
        enc = base64.b64encode(script.encode("utf-16-le")).decode()
        self._run([self._ps, "-NoProfile", "-NonInteractive", "-EncodedCommand", enc])


# ------------------------------------------------------------------------------ fan-out

class MultiNotifier:
    name = "multi"

    def __init__(self, sinks: list[Notifier]) -> None:
        self.sinks = sinks

    def send(self, target_label: str, alerts: list[Alert]) -> None:
        errors: list[str] = []
        for sink in self.sinks:
            try:
                sink.send(target_label, alerts)
            except Exception as e:                      # noqa: BLE001 -- report, never swallow
                errors.append(f"{sink.name}: {type(e).__name__}: {e}")
        if errors:
            raise NotifyError("; ".join(errors))


SINKS: dict[str, Callable[[], Notifier]] = {
    "console": ConsoleNotifier,
    "telegram": TelegramNotifier,
    "toast": WindowsToastNotifier,
}


def build(names: list[str], on_warning: Callable[[str], None] = lambda m: None) -> Notifier:
    """Construct the named sinks.

    A sink that cannot be constructed is a misconfiguration and must be surfaced at
    startup rather than on the first real alert. But killing the whole run because a
    *secondary* channel is unavailable would cost the price history and the channels
    that do work — so as long as ONE sink survives, the run continues with a loud
    warning. Only losing every sink is fatal: at that point you would be blind.
    """
    unknown = [n for n in names if n not in SINKS]
    if unknown:
        raise KeyError(f"unknown notifier(s) {unknown}; available: {sorted(SINKS)}")

    built, failed = [], []
    for n in names:
        try:
            built.append(SINKS[n]())
        except Exception as e:                          # noqa: BLE001
            failed.append(f"{n}: {type(e).__name__}: {e}")
    if failed and not built:
        raise NotifyError("every notifier failed to build — " + "; ".join(failed))
    for f in failed:
        on_warning(f"WARNING: notifier unavailable, continuing without it — {f}")
    return MultiNotifier(built)


def configured_names(cli: list[str] | None) -> list[str]:
    """CLI wins, then PRICEWATCH_NOTIFIERS (comma or space separated), then console."""
    if cli:
        return cli
    raw = config.get("PRICEWATCH_NOTIFIERS", "console")
    return [p for p in raw.replace(",", " ").split() if p]
