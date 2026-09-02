import base64
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from pricewatch import messages
from pricewatch.messages import DEFAULT_LANG
from pricewatch.models import Alert, Reading
from pricewatch.notify import (ConsoleNotifier, MultiNotifier, NotifyError,
                               TelegramNotifier, WindowsToastNotifier, configured_names,
                               is_permanent_chat_failure)
from pricewatch.subscribers import Store, Subscriber, SubscriberError
from pricewatch.telegram_api import TelegramApiError


def alert(key="lowest_ever", item="Gramado || Inteira", **overrides):
    """A real catalog alert -- an alert cannot carry a hand-written sentence any more.

    `item` is the only third-party value in the message: it is whatever the watched page
    called the ticket, and it is what the escaping tests below drive.
    """
    r = Reading(target_id="t", site="s", item=item, price_cents=25000, currency="BRL",
                quantity=5, captured_at="2026-09-01T00:00:00+00:00",
                source_url="https://example.test/e?a=1&b=2")
    params = {"item": item, "price": 25000, "qty": 5, "prior": 26000}
    params.update(overrides)
    return Alert(target_id="t", rule="lowest_ever", message_key=key, params=params, reading=r)


class TestTelegram(unittest.TestCase):
    def make(self, post):
        # Pinned to an EMPTY subscriber list on purpose. Left at the default, these
        # assertions would read the repo's real subscribers.json and start failing the
        # day a friend is added -- the same ambient-state trap that made
        # test_missing_chat_id_fails_at_construction pass for the wrong reason.
        return TelegramNotifier(token="TOK", chat_id="42", post=post,
                                store=Store("/nonexistent/subscribers.json"))

    def test_posts_to_the_right_endpoint_and_chat(self):
        seen = {}
        self.make(lambda u, p: seen.update(url=u, payload=p)).send("L", [alert()])
        self.assertEqual(seen["url"], "https://api.telegram.org/botTOK/sendMessage")
        self.assertEqual(seen["payload"]["chat_id"], "42")
        self.assertEqual(seen["payload"]["parse_mode"], "HTML")

    def test_escapes_markup_from_the_watched_site(self):
        """Ticket-class names are third-party text and must never render as markup."""
        body = self.make(lambda u, p: None).format("L", [alert(item="<b>&evil</b>")])
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
        """The escaping unit itself.

        It used to be reached by stuffing `body` into an alert's headline, which an
        alert can no longer carry: headlines are rendered from the catalog and hold
        money, never free text. The routing test below is what keeps this meaningful --
        without it, `send` could stop calling `build_script` and every assertion here
        would still pass.
        """
        return self.make(lambda argv: None).build_script(title, body)

    def sent_script(self, title, alerts):
        seen = {}
        self.make(lambda argv: seen.update(argv=argv)).send(title, alerts)
        enc = seen["argv"][seen["argv"].index("-EncodedCommand") + 1]
        return base64.b64decode(enc).decode("utf-16-le")

    def test_send_encodes_the_rendered_headlines_through_build_script(self):
        """The route the escaping tests below depend on -- and the label is escaped on
        the way, which is where an apostrophe actually reaches this sink now."""
        script = self.sent_script("Juan's board", [alert()])
        self.assertIn("NEW LOWEST", script)
        self.assertIn("Juan&apos;s board", script)
        self.assertNotIn("Juan's", script)

    def test_the_toast_is_english_even_when_a_subscriber_is_not(self):
        """This sink is yours alone. It has no recipient list and no language of its
        own: it renders DEFAULT_LANG, and adding a pt-BR friend cannot change that."""
        self.assertIn("NEW LOWEST", self.sent_script("L", [alert()]))

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


class TelegramFanOutTestCase(unittest.TestCase):
    """The telegram sink now has TWO tiers of recipient. They are not symmetric, and the
    asymmetry is the whole feature: exit 3 has to keep meaning "YOU were not told"."""

    OWNER = "42"

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.path = Path(self._dir.name) / "subscribers.json"
        self.store = Store(self.path)
        self.warnings = []

    def subs(self, *rows):
        """rows: (chat_id, name, enabled) or (chat_id, name, enabled, lang)"""
        self.store.save([Subscriber(name=r[1], chat_id=r[0], enabled=r[2],
                                    lang=r[3] if len(r) > 3 else DEFAULT_LANG)
                         for r in rows])
        return self.store

    def make(self, post, store=None, chat_id=None):
        return TelegramNotifier(token="TOK", chat_id=chat_id or self.OWNER, post=post,
                                store=store if store is not None else self.store,
                                on_warning=self.warnings.append)


class FakePost:
    """Records every send and can fail chosen chats. `sent` is in delivery order."""

    def __init__(self, fail=None):
        self.sent = []
        self.fail = fail or {}

    def __call__(self, url, payload):
        self.sent.append(payload)
        err = self.fail.get(payload["chat_id"])
        if err:
            raise err

    @property
    def chat_ids(self):
        return [p["chat_id"] for p in self.sent]


def refusal(code, description):
    return TelegramApiError(f"telegram refused ({code}) {description}",
                            error_code=code, description=description)


class TestTelegramFanOut(TelegramFanOutTestCase):
    def test_absent_file_is_owner_only(self):
        """The state every install starts in -- byte-identical to the old behaviour."""
        post = FakePost()
        self.make(post).send("L", [alert()])
        self.assertEqual(post.chat_ids, [self.OWNER])

    def test_owner_first_then_every_enabled_subscriber(self):
        self.subs(("111", "rafa", True), ("222", "bruno", True))
        post = FakePost()
        self.make(post).send("L", [alert()])
        self.assertEqual(post.chat_ids, [self.OWNER, "111", "222"])

    def test_everyone_on_one_language_receives_the_identical_message(self):
        """Language is the ONLY thing that is per-person -- no per-recipient targets,
        rules or prices. Two people reading the same language get the same bytes."""
        self.subs(("111", "rafa", True), ("222", "bruno", True))
        post = FakePost()
        self.make(post).send("L", [alert()])
        self.assertEqual(len({p["text"] for p in post.sent}), 1)
        self.assertEqual({p["parse_mode"] for p in post.sent}, {"HTML"})

    def test_disabled_subscribers_are_skipped(self):
        self.subs(("111", "rafa", True), ("222", "bruno", False))
        post = FakePost()
        self.make(post).send("L", [alert()])
        self.assertEqual(post.chat_ids, [self.OWNER, "111"])

    def test_the_owner_is_never_messaged_twice(self):
        """A hand-edited file can list the owner. Two identical alerts is the mild cost;
        the real one is that the copy would be best-effort, so a failure to reach YOU
        could be reported as a warning instead of exit 3."""
        self.subs((self.OWNER, "me again", True), ("111", "rafa", True))
        post = FakePost()
        self.make(post).send("L", [alert()])
        self.assertEqual(post.chat_ids, [self.OWNER, "111"])

    def test_no_alerts_sends_to_nobody(self):
        self.subs(("111", "rafa", True))
        post = FakePost()
        self.make(post).send("L", [])
        self.assertEqual(post.sent, [])


class TestTelegramLanguages(TelegramFanOutTestCase):
    """One firing, several languages. The rule cannot choose the sentence any more,
    because the sentence is not the same for everyone it reaches."""

    def sent_by_chat(self, post):
        return {p["chat_id"]: p["text"] for p in post.sent}

    def test_a_pt_br_subscriber_reads_portuguese_and_you_still_read_english(self):
        self.subs(("111", "rafa", True, "pt-BR"))
        post = FakePost()
        self.make(post).send("L", [alert()])
        by_chat = self.sent_by_chat(post)
        self.assertIn("NEW LOWEST", by_chat[self.OWNER])
        self.assertIn("NOVA MÍNIMA", by_chat["111"])
        self.assertNotIn("NEW LOWEST", by_chat["111"])

    def test_the_owner_language_does_not_follow_the_subscribers(self):
        """Your copy is the control. If it drifted with whoever you last approved, the
        fan-out would have no fixed reference to check anything against."""
        self.subs(("111", "rafa", True, "pt-BR"), ("222", "bruno", True, "pt-BR"))
        post = FakePost()
        self.make(post).send("L", [alert()])
        self.assertIn("NEW LOWEST", self.sent_by_chat(post)[self.OWNER])

    def test_mixed_languages_each_get_their_own(self):
        self.subs(("111", "rafa", True, "pt-BR"), ("222", "bruno", True, "en-US"))
        post = FakePost()
        self.make(post).send("L", [alert()])
        by_chat = self.sent_by_chat(post)
        self.assertIn("NOVA MÍNIMA", by_chat["111"])
        self.assertIn("NEW LOWEST", by_chat["222"])
        self.assertEqual(by_chat[self.OWNER], by_chat["222"], "same language, same bytes")

    def test_the_target_label_is_not_translated(self):
        """It is your own text out of the target file, already written how you want to
        read it -- and a label is what an alert is identified BY."""
        self.subs(("111", "rafa", True, "pt-BR"))
        post = FakePost()
        self.make(post).send("Rock in Rio 2026 — 04/09 · Gramado", [alert()])
        for text in self.sent_by_chat(post).values():
            self.assertIn("Rock in Rio 2026 — 04/09 · Gramado", text)

    def test_money_is_identical_across_languages(self):
        self.subs(("111", "rafa", True, "pt-BR"))
        post = FakePost()
        self.make(post).send("L", [alert()])
        for text in self.sent_by_chat(post).values():
            self.assertIn("R$ 250,00", text)

    def test_the_third_party_ticket_name_is_escaped_in_every_language(self):
        """Escaping happens at the sink, after rendering. A second language is a second
        code path through the same escape, and markup does not care which one it took."""
        self.subs(("111", "rafa", True, "pt-BR"))
        post = FakePost()
        self.make(post).send("L", [alert(item="<b>&evil</b>")])
        for text in self.sent_by_chat(post).values():
            self.assertNotIn("<b>&evil", text)
            self.assertIn("&lt;b&gt;&amp;evil", text)

    def test_owner_lang_can_be_overridden_for_the_add_time_delivery_test(self):
        """`--test <chat>` addresses a friend through the OWNER slot to make a failure
        loud. Left at DEFAULT_LANG it would report success on a setting it never
        exercised -- and your own copy of every real alert is English regardless, so
        nothing afterwards would catch it."""
        post = FakePost()
        TelegramNotifier(token="TOK", chat_id="111", post=post, store=self.store,
                         owner_lang="pt-BR").send("L", [alert()])
        self.assertIn("NOVA MÍNIMA", post.sent[0]["text"])


class TestTelegramRenderFailures(TelegramFanOutTestCase):
    """A broken template is not a delivery failure, and must not be charged like one.

    The catalog is validated at import, so reaching these states requires patching it.
    That is exactly why they are worth pinning: they are unreachable in a healthy tree
    and therefore never exercised by anything else."""

    def broken_lang(self, lang):
        """A catalog whose `lang` column interpolates something no rule supplies."""
        cat = {lg: dict(keys) for lg, keys in messages.CATALOG.items()}
        cat[lang]["lowest_ever"] = ("{nonexistent}", cat[lang]["lowest_ever"][1])
        return cat

    def test_one_broken_language_does_not_cost_the_other_recipients(self):
        """The MultiNotifier rule, two layers down: a friend's failure -- delivery or
        rendering -- is never allowed to become yours."""
        self.subs(("111", "rafa", True, "pt-BR"), ("222", "bruno", True, "en-US"))
        post = FakePost()
        with mock.patch.object(messages, "CATALOG", self.broken_lang("pt-BR")):
            self.make(post).send("L", [alert()])            # must not raise
        self.assertEqual(post.chat_ids, [self.OWNER, "222"],
                         "everyone whose language still renders was delivered to")
        self.assertTrue(any("rafa" in w for w in self.warnings))

    def test_a_broken_template_never_disables_anybody(self):
        """It is about the MESSAGE, not the chat -- the same distinction that keeps a
        400 "can't parse entities" from wiping the whole list."""
        self.subs(("111", "rafa", True, "pt-BR"))
        with mock.patch.object(messages, "CATALOG", self.broken_lang("pt-BR")):
            self.make(FakePost()).send("L", [alert()])
        self.assertTrue(self.store.load()[0].enabled)

    def test_a_broken_owner_language_still_raises_and_still_sends_to_friends(self):
        """Exit 3 means YOU were not told, and an unrenderable message is one of the
        ways that happens."""
        self.subs(("111", "rafa", True, "pt-BR"))
        post = FakePost()
        with mock.patch.object(messages, "CATALOG", self.broken_lang(DEFAULT_LANG)):
            with self.assertRaises(NotifyError):
                self.make(post).send("L", [alert()])
        self.assertEqual(post.chat_ids, ["111"], "the friend was still reached")


class TestTelegramTiers(TelegramFanOutTestCase):
    def test_owner_failure_raises_after_every_friend_was_still_attempted(self):
        """A dead owner chat must not cost the friends their message -- the MultiNotifier
        rule, one layer down."""
        self.subs(("111", "rafa", True), ("222", "bruno", True))
        post = FakePost(fail={self.OWNER: refusal(400, "Bad Request: chat not found")})
        with self.assertRaises(NotifyError) as cm:
            self.make(post).send("L", [alert()])
        self.assertIn(self.OWNER, str(cm.exception))
        self.assertEqual(post.chat_ids, [self.OWNER, "111", "222"])

    def test_a_friends_failure_does_not_raise(self):
        """Exit 3 means YOU were not told. A friend blocking the bot must not claim it."""
        self.subs(("111", "rafa", True))
        post = FakePost(fail={"111": refusal(403, "Forbidden: bot was blocked by the user")})
        self.make(post).send("L", [alert()])                    # must not raise
        self.assertIn(self.OWNER, post.chat_ids, "the owner was still delivered to")
        self.assertTrue(any("rafa" in w for w in self.warnings), "and it was reported")

    def test_a_403_disables_that_subscriber_in_the_file(self):
        self.subs(("111", "rafa", True), ("222", "bruno", True))
        post = FakePost(fail={"111": refusal(403, "Forbidden: bot was blocked by the user")})
        self.make(post).send("L", [alert()])
        by_id = {s.chat_id: s for s in self.store.load()}
        self.assertFalse(by_id["111"].enabled)
        self.assertIn("blocked", by_id["111"].disabled_reason)
        self.assertTrue(by_id["222"].enabled, "the healthy subscriber was left alone")

    def test_a_disabled_subscriber_is_not_retried_next_run(self):
        """The point of persisting it: otherwise every run warns about them forever."""
        self.subs(("111", "rafa", True))
        blocked = refusal(403, "Forbidden: bot was blocked by the user")
        self.make(FakePost(fail={"111": blocked})).send("L", [alert()])
        post = FakePost()
        self.make(post).send("L", [alert()])                    # a fresh run
        self.assertEqual(post.chat_ids, [self.OWNER])

    def test_chat_not_found_is_also_permanent(self):
        self.subs(("111", "rafa", True))
        post = FakePost(fail={"111": refusal(400, "Bad Request: chat not found")})
        self.make(post).send("L", [alert()])
        self.assertFalse(self.store.load()[0].enabled)

    def test_a_400_parse_error_disables_NOBODY(self):
        """⛔ The expensive mistake this guard exists for. "can't parse entities" is a 400
        like "chat not found", but it is about the MESSAGE, so it fails for every
        recipient at once: treating any 400 as permanent would wipe the whole subscriber
        list in a single run, from one ticket name the formatter mishandled."""
        self.subs(("111", "rafa", True), ("222", "bruno", True))
        broken = refusal(400, "Bad Request: can't parse entities")
        post = FakePost(fail={self.OWNER: broken, "111": broken, "222": broken})
        with self.assertRaises(NotifyError):
            self.make(post).send("L", [alert()])
        self.assertTrue(all(s.enabled for s in self.store.load()),
                        "a formatting bug disabled real subscribers")

    def test_a_rate_limit_does_not_disable(self):
        self.subs(("111", "rafa", True))
        post = FakePost(fail={"111": refusal(429, "Too Many Requests: retry after 30")})
        self.make(post).send("L", [alert()])
        self.assertTrue(self.store.load()[0].enabled)
        self.assertTrue(any("retry next run" in w for w in self.warnings))

    def test_a_network_error_does_not_disable(self):
        """It carries no error_code at all -- which is exactly how "the network" is told
        apart from "this chat"."""
        self.subs(("111", "rafa", True))
        post = FakePost(fail={"111": urllib.error.URLError("connection reset")})
        self.make(post).send("L", [alert()])
        self.assertTrue(self.store.load()[0].enabled)

    def test_a_store_write_failure_does_not_fail_the_delivery(self):
        """Bookkeeping, not delivery. Everyone reachable was reached; failing to RECORD
        that one person was not is not a reason to report the alert as undelivered."""
        class ReadOnlyStore(Store):
            def save(self, subs):
                raise OSError("read-only file system")

        store = ReadOnlyStore(self.path)
        self.subs(("111", "rafa", True))
        post = FakePost(fail={"111": refusal(403, "Forbidden: bot was blocked by the user")})
        self.make(post, store=store).send("L", [alert()])       # must not raise
        self.assertTrue(any("could not disable" in w for w in self.warnings))


class TestTelegramStartupFailures(TelegramFanOutTestCase):
    def test_a_comma_separated_chat_id_is_refused_and_says_where_friends_go(self):
        """Left alone it is sent verbatim as one chat id, and Telegram answers 400 "chat
        not found" on every run: a setup that looks configured and reaches nobody."""
        with self.assertRaises(NotifyError) as cm:
            self.make(FakePost(), chat_id="42,111")
        self.assertIn("subscribers.json", str(cm.exception))

    def test_a_corrupt_file_fails_at_construction_not_at_alert_time(self):
        self.path.write_text("{broken", encoding="utf-8")
        with self.assertRaises(SubscriberError):
            self.make(FakePost())

    def test_build_keeps_the_other_sinks_when_the_subscriber_file_is_corrupt(self):
        """The trade-off, stated: a corrupt list costs the telegram sink for the whole
        run -- yours included -- but never the run itself. Same degradation as a missing
        powershell.exe."""
        import os
        from pricewatch import notify
        self.path.write_text("{broken", encoding="utf-8")
        warnings = []
        with mock.patch.dict(os.environ, {"BOT_API_TOKEN": "TOK", "TELEGRAM_CHAT_ID": "42",
                                          "PRICEWATCH_SUBSCRIBERS": str(self.path)}):
            n = notify.build(["console", "telegram"], on_warning=warnings.append)
        self.assertEqual([s.name for s in n.sinks], ["console"])
        self.assertTrue(any("SubscriberError" in w for w in warnings))


class TestPermanenceClassification(unittest.TestCase):
    def test_403_is_permanent(self):
        self.assertTrue(is_permanent_chat_failure(
            refusal(403, "Forbidden: bot was blocked by the user")))

    def test_400_chat_not_found_is_permanent(self):
        self.assertTrue(is_permanent_chat_failure(refusal(400, "Bad Request: chat not found")))

    def test_other_400s_are_not(self):
        for desc in ("Bad Request: can't parse entities",
                     "Bad Request: message text is empty",
                     "Bad Request: message is too long"):
            self.assertFalse(is_permanent_chat_failure(refusal(400, desc)), desc)

    def test_transient_codes_are_not(self):
        for code in (429, 500, 502, 401):
            self.assertFalse(is_permanent_chat_failure(refusal(code, "x")), code)

    def test_an_exception_with_no_code_is_not(self):
        self.assertFalse(is_permanent_chat_failure(urllib.error.URLError("reset")))


if __name__ == "__main__":
    unittest.main()
