import unittest
from datetime import datetime, timedelta, timezone

from scripts.collect_items import apply_first_seen, parse_json_feed_items, parse_xml_items
from scripts.probe_sources import Endpoint


def endpoint(expected_format="rss"):
    return Endpoint(
        endpoint_id="feed",
        source_id="source",
        label="Flux",
        url="https://example.org/feed",
        access_method="http_get",
        expected_format=expected_format,
        content_scope="décisions|actualités",
        language="fr",
        enabled=True,
        last_manual_check="2026-08-27",
        notes="",
    )


SOURCE = {
    "name": "Source test",
    "source_class": "institution",
    "institution_level": "fédéral",
    "geography": "Belgique",
    "official_status": "official_public",
}


class FeedParsingTests(unittest.TestCase):
    def test_parses_rss_item_with_source_metadata(self):
        body = b"""<rss><channel><item>
        <title>Une decision publique</title>
        <link>https://example.org/news/1</link>
        <pubDate>Thu, 27 Aug 2026 04:30:00 GMT</pubDate>
        <description><![CDATA[<p>Un court <strong>extrait</strong>.</p>]]></description>
        <category>Budget</category></item></channel></rss>"""
        items = parse_xml_items(body, endpoint(), SOURCE, "2026-08-27T05:00:00Z")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["published_at"], "2026-08-27T04:30:00Z")
        self.assertEqual(items[0]["summary"], "Un court extrait.")
        self.assertEqual(items[0]["source_name"], "Source test")

    def test_parses_atom_alternate_link(self):
        body = b"""<feed xmlns='http://www.w3.org/2005/Atom'><entry>
        <title>Atom title</title><id>tag:example,1</id>
        <link rel='alternate' href='/article/1'/><updated>2026-08-27T04:30:00Z</updated>
        </entry></feed>"""
        items = parse_xml_items(body, endpoint("atom"), SOURCE, "2026-08-27T05:00:00Z")
        self.assertEqual(items[0]["url"], "https://example.org/article/1")

    def test_parses_json_feed(self):
        body = b'{"items":[{"id":"1","url":"https://example.org/1","title":"JSON title","date_published":"2026-08-27T04:30:00Z"}]}'
        items = parse_json_feed_items(body, endpoint("json_feed"), SOURCE, "2026-08-27T05:00:00Z")
        self.assertEqual(items[0]["title"], "JSON title")


class FirstSeenTests(unittest.TestCase):
    def test_distinguishes_bootstrap_existing_and_new(self):
        now = datetime(2026, 8, 27, 5, tzinfo=timezone.utc)
        bootstrap = [{"item_id": "old"}]
        state = apply_first_seen(bootstrap, {}, now, initialized=False)
        self.assertEqual(bootstrap[0]["observation_status"], "bootstrap")

        later = now + timedelta(days=1)
        items = [{"item_id": "old"}, {"item_id": "new"}]
        state = apply_first_seen(items, state, later, initialized=True)
        self.assertEqual(items[0]["observation_status"], "existing")
        self.assertEqual(items[1]["observation_status"], "new")
        self.assertEqual(state["old"]["seen_count"], 2)


if __name__ == "__main__":
    unittest.main()
