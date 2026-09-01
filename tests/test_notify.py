import base64
import unittest
from pathlib import Path
from unittest import mock

from pricewatch.models import Alert, Reading
from pricewatch.notify import (ConsoleNotifier, MultiNotifier, NotifyError,
                               TelegramNotifier, WindowsToastNotifier, configured_names)


def alert(headline="NEW LOWEST — R$ 250,00", detail="detail", item="Gramado || Inteira"):
    r = Reading(target_id="t", site="s", item=item, price_cents=25000, currency="BRL",
                quantity=5, captured_at="2026-09-01T00:00:00+00:00",
                source_url="https://example.test/e?a=1&b=2")
    return Alert(target_id="t", rule="lowest_ever", headline=headline, detail=detail, reading=r)


class TestTelegram(unittest.TestCase):
    def make(self, post):
        return TelegramNotifier(token="TOK", chat_id="42", post=post)

    def test_posts_to_the_right_endpoint_and_chat(self):
        seen = {}
        self.make(lambda u, p: seen.update(url=u, payload=p)).send("L", [alert()])
        self.assertEqual(seen["url"], "https://api.telegram.org/botTOK/sendMessage")
        self.assertEqual(seen["payload"]["chat_id"], "42")
        self.assertEqual(seen["payload"]["parse_mode"], "HTML")

    def test_escapes_markup_from_the_watched_site(self):
        """Ticket-class names are third-party text and must never render as markup."""
        body = self.make(lambda u, p: None).format("L", [alert(item="x", detail="<b>&evil</b>")])
        self.assertNotIn("<b>&evil", body)
        self.assertIn("&lt;b&gt;&amp;evil", body)

    def test_ampersand_in_the_url_is_escaped(self):
        body = self.make(lambda u, p: None).format("L", [alert()])
        self.assertIn("a=1&amp;b=2", body)

    def test_no_alerts_sends_nothing(self):
        calls = []
        self.make(lambda u, p: calls.append(p)).send("L", [])
        self.assertEqual(calls, [])

    def test_missing_chat_id_fails_at_construction(self):
        """Not at alert time -- the one message you cared about must not be the one lost.

        Pinned against an EMPTY env on purpose: this test passed for the wrong reason
        until the real .env gained a chat id, which made it read ambient state.
        """
        import os
        from pricewatch import config
        with mock.patch.object(config, "DEFAULT_ENV_PATH", Path("/nonexistent/.env")), \
             mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(KeyError):
                TelegramNotifier(token="TOK", chat_id=None, post=lambda u, p: None)


class TestWindowsToast(unittest.TestCase):
    def make(self, runner):
        return WindowsToastNotifier(runner=runner, powershell="/fake/powershell.exe")

    def script_for(self, title, body):
        seen = {}
        self.make(lambda argv: seen.update(argv=argv)).send(title, [alert(headline=body)])
        enc = seen["argv"][seen["argv"].index("-EncodedCommand") + 1]
        return base64.b64decode(enc).decode("utf-16-le")

    def test_apostrophe_cannot_break_out_of_the_powershell_string(self):
        """A ticket name with ' would otherwise terminate the PS string early."""
        script = self.script_for("Juan's board", "it's cheap")
        self.assertNotIn("Juan's", script)
        self.assertIn("Juan&apos;s", script)

    def test_interpolated_text_contributes_no_quotes_at_all(self):
        """The property that matters: user text cannot change the script's quoting."""
        risky = self.script_for("Juan's board", "it's cheap")
        safe = self.script_for("Juan board", "it cheap")
        self.assertEqual(risky.count("'"), safe.count("'"))
        self.assertEqual(risky.count('"'), safe.count('"'))

    def test_xml_metacharacters_are_escaped(self):
        script = self.script_for("<a>", "b & c")
        self.assertIn("&lt;a&gt;", script)
        self.assertIn("b &amp; c", script)

    def test_absent_powershell_is_a_loud_construction_error(self):
        """Auto-detect finds it on this machine, so absence has to be simulated --
        both on PATH and at the known Windows locations."""
        with mock.patch("pricewatch.notify.shutil.which", return_value=None), \
             mock.patch("pricewatch.notify.os.path.exists", return_value=False):
            with self.assertRaises(NotifyError) as cm:
                WindowsToastNotifier(runner=lambda a: None, powershell=None)
        self.assertIn("powershell.exe not found", str(cm.exception))

    def test_falls_back_to_a_known_path_when_PATH_lacks_it(self):
        """The cron regression: cron's PATH is ~/usr/bin:/bin and hides powershell.exe.

        Before this fallback existed, `build()` raised at startup and the entire run
        aborted -- losing the prices and the Telegram alert along with the toast.
        """
        with mock.patch("pricewatch.notify.shutil.which", return_value=None), \
             mock.patch("pricewatch.notify.os.path.exists",
                        side_effect=lambda p: p == WindowsToastNotifier.CANDIDATES[0]):
            n = WindowsToastNotifier(runner=lambda a: None, powershell=None)
        self.assertEqual(n._ps, WindowsToastNotifier.CANDIDATES[0])

    def test_autodetect_is_used_when_powershell_is_not_given(self):
        with mock.patch("pricewatch.notify.shutil.which", return_value="/x/ps.exe"):
            n = WindowsToastNotifier(runner=lambda a: None, powershell=None)
        self.assertEqual(n._ps, "/x/ps.exe")


class TestMulti(unittest.TestCase):
    class Boom:
        name = "boom"
        def send(self, *_): raise RuntimeError("nope")

    class Ok:
        name = "ok"
        def __init__(self): self.calls = 0
        def send(self, *_): self.calls += 1

    def test_a_failing_sink_does_not_stop_the_others(self):
        ok = self.Ok()
        with self.assertRaises(NotifyError):
            MultiNotifier([self.Boom(), ok]).send("L", [alert()])
        self.assertEqual(ok.calls, 1, "the healthy sink must still have been tried")

    def test_error_names_every_failing_sink(self):
        with self.assertRaises(NotifyError) as cm:
            MultiNotifier([self.Boom(), self.Boom()]).send("L", [alert()])
        self.assertEqual(str(cm.exception).count("boom"), 2)

    def test_all_healthy_raises_nothing(self):
        MultiNotifier([self.Ok(), ConsoleNotifier()]).send("L", [alert()])


class TestSelection(unittest.TestCase):
    def test_cli_wins(self):
        self.assertEqual(configured_names(["toast"]), ["toast"])

    def test_default_is_console(self):
        import os
        os.environ["PRICEWATCH_NOTIFIERS"] = "console"
        self.addCleanup(lambda: os.environ.pop("PRICEWATCH_NOTIFIERS", None))
        self.assertEqual(configured_names(None), ["console"])

    def test_comma_and_space_both_parse(self):
        import os
        os.environ["PRICEWATCH_NOTIFIERS"] = "console, telegram toast"
        self.addCleanup(lambda: os.environ.pop("PRICEWATCH_NOTIFIERS", None))
        self.assertEqual(configured_names(None), ["console", "telegram", "toast"])


if __name__ == "__main__":
    unittest.main()


class TestBuildDegradation(unittest.TestCase):
    """A secondary channel being unavailable must not cost the run."""

    def test_one_broken_sink_warns_and_continues(self):
        from pricewatch import notify
        warnings = []
        with mock.patch.dict(notify.SINKS, {"boom": lambda: (_ for _ in ()).throw(RuntimeError("x"))}):
            n = notify.build(["console", "boom"], on_warning=warnings.append)
        self.assertEqual(len(n.sinks), 1)
        self.assertEqual(len(warnings), 1)
        self.assertIn("continuing without it", warnings[0])

    def test_losing_every_sink_is_fatal(self):
        from pricewatch import notify
        with mock.patch.dict(notify.SINKS, {"boom": lambda: (_ for _ in ()).throw(RuntimeError("x"))}):
            with self.assertRaises(NotifyError):
                notify.build(["boom"])

    def test_unknown_sink_name_is_a_key_error(self):
        from pricewatch import notify
        with self.assertRaises(KeyError):
            notify.build(["nope"])
