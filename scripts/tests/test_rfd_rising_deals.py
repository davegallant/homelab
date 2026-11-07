import importlib.util
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from pathlib import Path

spec = importlib.util.spec_from_file_location('rfd_digest', Path('kubernetes/apps/rfd-rising-deals/chart/files/digest.py'))
digest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(digest)


class DigestTests(unittest.TestCase):
    def test_rank_recent_by_upvotes_per_hour(self):
        now = datetime(2026, 11, 7, 12, tzinfo=timezone.utc)
        topics = [
            {'forum_id': 9, 'topic_id': 1, 'title': 'A', 'web_path': '/a-1/', 'post_time': '2026-11-07T10:00:00Z', 'Votes': {'total_up': 20}},
            {'forum_id': 9, 'topic_id': 2, 'title': 'B', 'web_path': '/b-2/', 'post_time': '2026-11-07T11:00:00Z', 'Votes': {'total_up': 15}},
            {'forum_id': 9, 'topic_id': 3, 'title': 'Old', 'web_path': '/c-3/', 'post_time': '2026-11-05T11:00:00Z', 'Votes': {'total_up': 999}},
            {'forum_id': 8, 'topic_id': 4, 'title': 'Contest', 'web_path': '/d-4/', 'post_time': '2026-11-07T11:00:00Z', 'Votes': {'total_up': 999}},
        ]
        self.assertEqual([x['id'] for x in digest.rank(topics, now)], [2, 1])

    def test_reject_external_and_invalid_entries(self):
        now = datetime(2026, 11, 7, tzinfo=timezone.utc)
        self.assertEqual(digest.rank([{'forum_id': 9, 'topic_id': 1, 'title': 'bad', 'web_path': '//evil', 'post_time': '2026-11-06T23:00:00Z', 'Votes': {'total_up': 1}}], now), [])

    def test_model_price_must_appear_in_source_title(self):
        item = {'title': 'Acme $10 special', 'id': 1}
        self.assertEqual(digest.validate_format(item, {'id': 1, 'title': 'Acme', 'price': '$10'}), ('Acme', '$10'))
        with self.assertRaises(ValueError):
            digest.validate_format(item, {'id': 1, 'title': 'Acme', 'price': '$99'})

    def test_model_cannot_add_links(self):
        with self.assertRaises(ValueError):
            digest.validate_format({'id': 1, 'title': 'Acme'}, {'id': 1, 'title': '[Acme](https://evil)', 'price': 'Price not listed'})

    def test_model_cannot_invent_title_words(self):
        with self.assertRaises(ValueError):
            digest.validate_format({'id': 1, 'title': 'Acme cable'}, {'id': 1, 'title': 'Acme laptop', 'price': 'Price not listed'})

    def test_model_title_may_include_parentheses(self):
        self.assertEqual(digest.validate_format({'id': 1, 'title': 'Acme cable (2 pack)'},
                                               {'id': 1, 'title': 'Acme cable (2 pack)', 'price': 'Price not listed'}),
                         ('Acme cable (2 pack)', 'Price not listed'))

    def test_model_title_may_preserve_source_brackets(self):
        self.assertEqual(digest.validate_format({'id': 1, 'title': '[Targeted] Acme cable'},
                                               {'id': 1, 'title': '[Targeted] Acme cable', 'price': 'Price not listed'}),
                         ('[Targeted] Acme cable', 'Price not listed'))

    def test_model_may_separate_concatenated_title_words(self):
        self.assertEqual(digest.validate_format({'id': 1, 'title': 'Finger BrakeDEWALT tape'},
                                               {'id': 1, 'title': 'Finger Brake DEWALT tape', 'price': 'Price not listed'}),
                         ('Finger Brake DEWALT tape', 'Price not listed'))

    def test_invalid_model_item_falls_back_to_source(self):
        item = {'id': 1, 'title': 'Acme cable $12.99'}
        self.assertEqual(digest.safe_format(item, {'id': 1, 'title': 'Imaginary laptop', 'price': '$999'}),
                         ('Acme cable', '$12.99'))

    def test_fallback_does_not_invent_a_price(self):
        item = {'id': 1, 'title': 'Acme cable'}
        self.assertEqual(digest.safe_format(item, {'id': 1, 'title': 'Imaginary laptop', 'price': '$999'}),
                         ('Acme cable', 'Price not listed'))

    def test_gotify_uses_header_and_markdown_payload(self):
        with patch.object(digest, 'urlopen') as urlopen:
            urlopen.return_value.__enter__.return_value.status = 200
            digest.send_gotify('example digest', 'secret-token')
            request = urlopen.call_args.args[0]
            self.assertEqual(request.get_header('X-gotify-key'), 'secret-token')
            self.assertEqual(request.full_url, 'https://gotify.davegallant.ca/message')
            self.assertIn(b'example digest', request.data)


if __name__ == '__main__':
    unittest.main()
