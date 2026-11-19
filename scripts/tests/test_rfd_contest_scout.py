import importlib.util
import os
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SCOUT = REPO / "kubernetes/apps/rfd-contest-scout/chart/files/scout.py"
SPEC = importlib.util.spec_from_file_location("scout", SCOUT)
scout = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scout)

FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>https://forums.redflagdeals.com/viewtopic.php?t=2832741&amp;p=41371402#p41371402</id>
    <published>2026-11-18T16:59:14-05:00</published>
    <title type="html"><![CDATA[[Daily] 2026/12/31 ShopBeerGear Lift Passes Contest [AB and SK Only]]]></title>
  </entry>
  <entry>
    <id>https://forums.redflagdeals.com/viewtopic.php?t=2832700</id>
    <published>2026-11-17T10:00:00-05:00</published>
    <title type="html"><![CDATA[[Once] 2026-12-01 Example &amp; Co Contest]]></title>
  </entry>
  <entry>
    <id>https://example.com/not-rfd</id>
    <published>2026-11-17T10:00:00-05:00</published>
    <title type="html"><![CDATA[[Once] Not RFD]]></title>
  </entry>
</feed>
"""


class ParseTests(unittest.TestCase):
    def test_thread_id_from_query_and_path(self):
        self.assertEqual(scout.parse_thread_id("https://forums.redflagdeals.com/viewtopic.php?t=2832741&p=1"), "2832741")
        self.assertEqual(scout.parse_thread_id("https://forums.redflagdeals.com/topic-name-2832741/"), "2832741")

    def test_thread_id_rejects_other_hosts(self):
        with self.assertRaises(ValueError):
            scout.parse_thread_id("https://example.com/viewtopic.php?t=2832741")

    def test_expiry_and_frequency_from_title(self):
        self.assertEqual(scout.expiry_from_title("[Once] 2026/12/31 Contest"), "2026-12-31")
        self.assertEqual(scout.expiry_from_title("[Once] 2026-2-3 Contest"), "2026-02-03")
        self.assertIsNone(scout.expiry_from_title("[Once] 2026/02/31 Contest"))
        self.assertIsNone(scout.expiry_from_title("[Once] Contest"))
        self.assertEqual(scout.frequency_from_title("[Daily] Contest"), "daily")
        self.assertEqual(scout.frequency_from_title("Contest"), "unknown")

    def test_feed_keeps_rfd_threads_and_decodes_entities(self):
        threads = scout.parse_feed(FEED)
        self.assertEqual([t["thread_id"] for t in threads], ["2832741", "2832700"])
        self.assertEqual(threads[1]["title"], "[Once] 2026-12-01 Example & Co Contest")
        self.assertEqual(threads[1]["url"], "https://forums.redflagdeals.com/viewtopic.php?t=2832700")

    def test_region_note_is_parsed_and_does_not_exclude(self):
        title = "[Once] 2026/11/22 Whistler Film Festival &quot;WFF&quot; (IG)(No QC)"
        self.assertEqual(scout.region_note_from_title(scout.html.unescape(title)), "No QC")
        self.assertIsNone(scout.region_note_from_title("[Once] Contest"))
        self.assertTrue(scout.is_ontario_eligible(title))

    def test_empty_feed_is_an_error(self):
        with self.assertRaises(ValueError):
            scout.parse_feed(b'<feed xmlns="http://www.w3.org/2005/Atom"></feed>')


class EligibilityTests(unittest.TestCase):
    def test_other_province_only_contests_are_dropped(self):
        self.assertFalse(scout.is_ontario_eligible("[Daily] Contest [AB and SK Only]"))
        self.assertFalse(scout.is_ontario_eligible("[Once] Contest - Quebec residents only"))
        self.assertFalse(scout.is_ontario_eligible("[Once] Contest excluding Ontario"))

    def test_national_and_ontario_contests_are_kept(self):
        self.assertTrue(scout.is_ontario_eligible("[Once] Contest open to Canadians"))
        self.assertTrue(scout.is_ontario_eligible("[Once] Ontario only contest"))


class RankAndRenderTests(unittest.TestCase):
    def test_expiry_soonest_then_once_then_newest(self):
        rows = [
            {"expires_on": None, "frequency": "once", "published_at": "2026-11-18T10:00:00-05:00"},
            {"expires_on": "2026-12-05", "frequency": "daily", "published_at": "2026-11-01T10:00:00-05:00"},
            {"expires_on": "2026-12-05", "frequency": "once", "published_at": "2026-11-02T10:00:00-05:00"},
            {"expires_on": "2026-12-05", "frequency": "once", "published_at": "2026-11-03T10:00:00-05:00"},
        ]
        ranked = scout.rank(rows)
        self.assertEqual([r["published_at"][:10] for r in ranked],
                         ["2026-11-03", "2026-11-02", "2026-11-01", "2026-11-18"])

    def test_digest_escapes_markdown_and_strips_prefix(self):
        item = {"kind": "new", "title": "[Once] 2026/12/31 Win *big*!", "url": "https://forums.redflagdeals.com/viewtopic.php?t=1",
                "expires_on": "2026-12-31", "frequency": "once", "region_note": None}
        text = scout.render_digest([item], date(2026, 11, 18))
        self.assertIn("**New**", text)
        self.assertIn(r"- [Win \*big\*\!](https://forums.redflagdeals.com/viewtopic.php?t=1) — Dec 31, 2026 · once", text)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "contest-scout.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_threads_are_notified_once(self):
        now = datetime(2026, 11, 18, 13, 0, tzinfo=timezone.utc)
        today = date(2026, 11, 18)
        threads = scout.parse_feed(FEED)
        conn = scout.open_db(self.path)
        try:
            with conn:
                scout.save_threads(conn, threads, now.isoformat())
                first = scout.candidates(conn, today)
                # The AB/SK-only thread is not Ontario-eligible.
                self.assertEqual([c["thread_id"] for c in first], ["2832700"])
                scout.mark_notified(conn, first, now.isoformat(), today)
            with conn:
                scout.save_threads(conn, threads, now.isoformat())
            self.assertEqual(scout.candidates(conn, today), [])
        finally:
            conn.close()

    def test_expired_contests_are_dropped(self):
        conn = scout.open_db(self.path)
        try:
            with conn:
                scout.save_threads(conn, scout.parse_feed(FEED), "2026-11-18T13:00:00+00:00")
            self.assertEqual(scout.candidates(conn, date(2026, 12, 2)), [])
        finally:
            conn.close()

    def test_ending_soon_reminder_sent_once(self):
        now = datetime(2026, 11, 18, 13, 0, tzinfo=timezone.utc)
        conn = scout.open_db(self.path)
        try:
            with conn:
                scout.save_threads(conn, scout.parse_feed(FEED), now.isoformat())
                items = scout.candidates(conn, date(2026, 11, 18))
                self.assertEqual([i["kind"] for i in items], ["new"])
                scout.mark_notified(conn, items, now.isoformat(), date(2026, 11, 18))
            # 2026-12-01 is 13 days out on 11-18: no reminder yet.
            self.assertEqual(scout.candidates(conn, date(2026, 11, 18)), [])
            # Two days before expiry the reminder fires once.
            ending = scout.candidates(conn, date(2026, 11, 29))
            self.assertEqual([i["kind"] for i in ending], ["ending"])
            scout.mark_notified(conn, ending, now.isoformat(), date(2026, 11, 29))
            self.assertEqual(scout.candidates(conn, date(2026, 11, 29)), [])
        finally:
            conn.close()


class GotifyTests(unittest.TestCase):
    def test_apprise_url_must_target_gotify_host(self):
        self.assertEqual(scout.gotify_target("gotifys://gotify.davegallant.ca/ABC123?format=markdown"),
                         ("https://gotify.davegallant.ca/message", "ABC123"))
        with self.assertRaises(ValueError):
            scout.gotify_target("gotifys://example.com/ABC123")
        with self.assertRaises(ValueError):
            scout.gotify_target("https://gotify.davegallant.ca/ABC123")
        with self.assertRaises(ValueError):
            scout.gotify_target("gotifys://gotify.davegallant.ca/")


if __name__ == "__main__":
    unittest.main()
