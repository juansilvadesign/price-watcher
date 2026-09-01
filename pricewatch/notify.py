"""Notification sinks.

Three sinks ship: `console`, `telegram`, `toast` (Windows, via WSL). Select any
combination — `--notifier console telegram toast`, or set `PRICEWATCH_NOTIFIERS`
in `.env` so a cron line stays short.

Two rules the harness depends on:

* **Every sink is attempted, even after one fails.** A Telegram outage must not
  cost you the toast that would have reached you anyway.
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
import json
import shutil
import subprocess
import urllib.parse
import urllib.request
import xml.sax.saxutils as _xml
from typing import Callable, Protocol

from . import config
from .models import Alert

TIMEOUT_S = 20


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
    data = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        body = json.load(resp)
    if not body.get("ok"):
        raise NotifyError(f"telegram refused the message: {body}")


class TelegramNotifier:
    """Sends to ONE chat id — yours, the destination, not the bot's own id.

    A bot cannot open a conversation. The chat must have messaged the bot at least
    once, which is why `tools/telegram_chat_id.py` exists.
    """

    name = "telegram"

    def __init__(self, token: str | None = None, chat_id: str | None = None,
                 post: Callable[[str, dict], None] = _urllib_post) -> None:
        self.token = token or config.require(
            "BOT_API_TOKEN", "Create a bot with @BotFather to get one.")
        self.chat_id = chat_id or config.require(
            "TELEGRAM_CHAT_ID",
            "This is YOUR chat id, not the bot's. Message the bot once, then run "
            "`python3 tools/telegram_chat_id.py`.")
        self._post = post

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
        self._post(
            f"https://api.telegram.org/bot{self.token}/sendMessage",
            {"chat_id": self.chat_id,
             "text": self.format(target_label, alerts),
             "parse_mode": "HTML",
             "disable_web_page_preview": "true"},
        )


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

    def __init__(self, runner: Callable[[list[str]], None] = _powershell_run,
                 powershell: str | None = None) -> None:
        self._run = runner
        self._ps = powershell or shutil.which("powershell.exe")
        if not self._ps:
            raise NotifyError(
                "powershell.exe not found on PATH — the 'toast' sink only works from "
                "WSL on a Windows host. Drop it from --notifier / PRICEWATCH_NOTIFIERS.")

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


def build(names: list[str]) -> Notifier:
    unknown = [n for n in names if n not in SINKS]
    if unknown:
        raise KeyError(f"unknown notifier(s) {unknown}; available: {sorted(SINKS)}")
    return MultiNotifier([SINKS[n]() for n in names])


def configured_names(cli: list[str] | None) -> list[str]:
    """CLI wins, then PRICEWATCH_NOTIFIERS (comma or space separated), then console."""
    if cli:
        return cli
    raw = config.get("PRICEWATCH_NOTIFIERS", "console")
    return [p for p in raw.replace(",", " ").split() if p]
