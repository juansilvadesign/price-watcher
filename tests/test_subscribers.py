import json
import tempfile
import unittest
from pathlib import Path

from pricewatch.subscribers import Store, Subscriber, SubscriberError, parse


class StoreTestCase(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.path = Path(self._dir.name) / "subscribers.json"
        self.store = Store(self.path)

    def write(self, text: str) -> None:
        self.path.write_text(text, encoding="utf-8")

    def write_json(self, obj) -> None:
        self.write(json.dumps(obj))


class TestAbsentIsNotCorrupt(StoreTestCase):
    """The invariant this module exists for: an absent list is DATA, a corrupt one is
    blindness. `AdapterError` vs `[]`, one layer up."""

    def test_absent_file_is_nobody_subscribed(self):
        self.assertEqual(self.store.load(), [])
        self.assertEqual(self.store.enabled(), [])

    def test_corrupt_file_raises_instead_of_reading_as_empty(self):
        self.write("{not json at all")
        with self.assertRaises(SubscriberError) as cm:
            self.store.load()
        self.assertIn("invalid JSON", str(cm.exception))

    def test_a_truncated_write_raises_rather_than_silently_losing_everyone(self):
        """The shape an interrupted save would leave behind, if save() were not atomic."""
        self.write('{"subscribers": [{"name": "rafa", "chat_i')
        with self.assertRaises(SubscriberError):
            self.store.load()


class TestParsing(StoreTestCase):
    def test_reads_entries_and_defaults_enabled_to_true(self):
        self.write_json({"subscribers": [{"name": "rafa", "chat_id": "111"}]})
        (s,) = self.store.load()
        self.assertEqual((s.name, s.chat_id, s.enabled), ("rafa", "111", True))

    def test_integer_chat_id_is_accepted_and_normalised_to_a_string(self):
        """Telegram sends ints on the wire; a hand-edited file will carry one. Mixing the
        two types makes an id compare unequal to itself and the dedup silently miss."""
        self.write_json({"subscribers": [{"chat_id": 1122334455}]})
        self.assertEqual(self.store.load()[0].chat_id, "1122334455")

    def test_a_nameless_entry_still_identifies_itself(self):
        self.write_json({"subscribers": [{"chat_id": "111"}]})
        self.assertEqual(self.store.load()[0].name, "chat:111")

    def test_missing_chat_id_refuses_to_load(self):
        self.write_json({"subscribers": [{"name": "rafa"}]})
        with self.assertRaises(SubscriberError) as cm:
            self.store.load()
        self.assertIn("chat_id", str(cm.exception))

    def test_a_bare_true_chat_id_is_refused(self):
        """`isinstance(True, int)` is True, so an unguarded coercion gives chat id "1" --
        an entry that loads clean and addresses a chat that is not the one intended.
        Same trap registry.py guards on price_brl."""
        self.write_json({"subscribers": [{"name": "rafa", "chat_id": True}]})
        with self.assertRaises(SubscriberError):
            self.store.load()

    def test_a_quoted_false_for_enabled_is_refused(self):
        """A string "false" is truthy: bool() would ARM an entry its author switched off."""
        self.write_json({"subscribers": [{"chat_id": "111", "enabled": "false"}]})
        with self.assertRaises(SubscriberError) as cm:
            self.store.load()
        self.assertIn("truthy", str(cm.exception))

    def test_duplicate_chat_id_is_refused(self):
        """Both copies receive every alert, and set_enabled would only ever fix one."""
        self.write_json({"subscribers": [{"chat_id": "111"}, {"chat_id": "111"}]})
        with self.assertRaises(SubscriberError) as cm:
            self.store.load()
        self.assertIn("twice", str(cm.exception))

    def test_wrong_root_shape_is_refused(self):
        self.write_json([{"chat_id": "111"}])
        with self.assertRaises(SubscriberError):
            self.store.load()

    def test_a_subscriber_that_is_not_an_object_is_refused(self):
        self.write_json({"subscribers": ["111"]})
        with self.assertRaises(SubscriberError):
            self.store.load()

    def test_parse_names_the_offending_entry(self):
        with self.assertRaises(SubscriberError) as cm:
            parse('{"subscribers": [{"chat_id": "1"}, {"name": "x"}]}', "f.json")
        self.assertIn("f.json[1]", str(cm.exception))


class TestMutations(StoreTestCase):
    def test_add_then_read_back(self):
        sub = self.store.add("111", "rafa")
        self.assertEqual(sub.name, "rafa")
        self.assertTrue(sub.added_at, "an add records when it happened")
        self.assertEqual([s.chat_id for s in self.store.load()], ["111"])

    def test_add_refuses_a_duplicate(self):
        self.store.add("111", "rafa")
        with self.assertRaises(SubscriberError):
            self.store.add("111", "rafa again")

    def test_remove_reports_whether_it_did_anything(self):
        self.store.add("111", "rafa")
        self.assertTrue(self.store.remove("111"))
        self.assertFalse(self.store.remove("111"))

    def test_disable_records_the_reason_and_enable_clears_it(self):
        self.store.add("111", "rafa")
        self.assertTrue(self.store.disable("111", "blocked the bot"))
        (s,) = self.store.load()
        self.assertFalse(s.enabled)
        self.assertEqual(s.disabled_reason, "blocked the bot")

        self.assertTrue(self.store.set_enabled("111", True))
        (s,) = self.store.load()
        self.assertTrue(s.enabled)
        self.assertEqual(s.disabled_reason, "", "a re-enabled entry keeps no stale reason")

    def test_disabling_twice_reports_no_change(self):
        self.store.add("111", "rafa")
        self.store.disable("111", "blocked")
        self.assertFalse(self.store.disable("111", "blocked"))

    def test_disabling_an_unknown_id_changes_nothing(self):
        self.store.add("111", "rafa")
        self.assertFalse(self.store.disable("999", "blocked"))
        self.assertTrue(self.store.load()[0].enabled)

    def test_save_leaves_no_temp_file_behind(self):
        self.store.add("111", "rafa")
        self.assertEqual(sorted(p.name for p in Path(self._dir.name).iterdir()),
                         ["subscribers.json"])

    def test_disable_preserves_a_change_made_after_this_process_loaded(self):
        """Two crontab lines fire in the same minute (`* * * * *` and `*/5 * * * *`), so
        two runs hold this file at once. Writing back a snapshot taken at startup would
        silently revert whatever the other run just wrote."""
        self.store.add("111", "rafa")
        self.store.add("222", "bruno")
        snapshot = self.store.load()
        self.assertTrue(all(s.enabled for s in snapshot), "both start enabled")

        Store(self.path).disable("222", "blocked")      # the other run, same minute
        self.store.disable("111", "blocked")            # this run, holding `snapshot`

        by_id = {s.chat_id: s for s in self.store.load()}
        self.assertFalse(by_id["222"].enabled, "a concurrent disable was reverted")
        self.assertFalse(by_id["111"].enabled)

    def test_round_trip_through_the_file_is_lossless(self):
        self.store.save([Subscriber(name="rafa", chat_id="111", enabled=False,
                                    added_at="2026-09-02T00:00:00+00:00",
                                    disabled_reason="blocked")])
        (s,) = self.store.load()
        self.assertEqual((s.name, s.chat_id, s.enabled, s.added_at, s.disabled_reason),
                         ("rafa", "111", False, "2026-09-02T00:00:00+00:00", "blocked"))

    def test_a_healthy_entry_carries_no_disabled_reason_key(self):
        self.store.add("111", "rafa")
        self.assertNotIn("disabled_reason", self.path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
