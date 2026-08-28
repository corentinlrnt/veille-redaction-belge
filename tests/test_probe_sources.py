import csv
import tempfile
import unittest
from pathlib import Path

from scripts.probe_sources import (
    ConfigurationError,
    MetadataHTMLParser,
    ProbeResult,
    build_summary,
    detect_format,
    format_matches_expected,
    load_registry,
    newest_iso,
    parse_xml_metadata,
)


class FormatDetectionTests(unittest.TestCase):
    def test_detects_html_from_body(self):
        self.assertEqual(detect_format(b"<!doctype html><html></html>", "text/plain"), "html")

    def test_detects_rss_and_atom(self):
        self.assertEqual(detect_format(b"<rss version='2.0'/>", "application/rss+xml"), "rss")
        self.assertEqual(
            detect_format(b"<feed xmlns='http://www.w3.org/2005/Atom'/>", "application/xml"),
            "atom",
        )

    def test_detects_json(self):
        self.assertEqual(detect_format(b'{"items": []}', "text/plain"), "json")

    def test_matches_explicit_adapter_formats(self):
        self.assertTrue(format_matches_expected("wp_json", "json"))
        self.assertTrue(format_matches_expected("html_articles", "html"))
        self.assertFalse(format_matches_expected("html_articles", "rss"))


class MetadataTests(unittest.TestCase):
    def test_discovers_relative_feed(self):
        parser = MetadataHTMLParser("https://example.org/news/")
        parser.feed(
            '<link rel="alternate" type="application/rss+xml" href="../feed.xml">'
            '<time datetime="2026-08-27T06:00:00+02:00"></time>'
        )
        self.assertEqual(parser.feed_urls, ["https://example.org/feed.xml"])
        self.assertEqual(parser.time_values, ["2026-08-27T06:00:00+02:00"])

    def test_extracts_feed_count_and_latest_date(self):
        body = b"""<?xml version='1.0'?>
        <rss><channel>
          <item><pubDate>Wed, 26 Aug 2026 05:00:00 GMT</pubDate></item>
          <item><pubDate>Thu, 27 Aug 2026 04:30:00 GMT</pubDate></item>
        </channel></rss>"""
        count, latest = parse_xml_metadata(body)
        self.assertEqual(count, 2)
        self.assertEqual(latest, "2026-08-27T04:30:00Z")

    def test_normalizes_mixed_dates(self):
        self.assertEqual(
            newest_iso(["Wed, 26 Aug 2026 05:00:00 GMT", "2026-08-27T06:00:00+02:00"]),
            "2026-08-27T04:00:00Z",
        )

    def test_builds_summary(self):
        results = [
            ProbeResult("one", "s", "Source", "institution", "fédéral", "A", "https://a", access_status="ok", detected_format="html"),
            ProbeResult("two", "s", "Source", "institution", "fédéral", "B", "https://b", access_status="http_error", detected_format="unknown"),
        ]
        summary = build_summary(results, 2)
        self.assertEqual(summary["ok"], 1)
        self.assertEqual(summary["errors"], 1)
        self.assertEqual(summary["format_mismatches"], 0)


class RegistryTests(unittest.TestCase):
    def test_rejects_unknown_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = root / "sources.csv"
            endpoints = root / "endpoints.csv"
            with sources.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "source_id", "name", "source_class", "institution_level",
                        "geography", "languages", "homepage_url", "official_status",
                        "last_manual_check", "notes",
                    ],
                )
                writer.writeheader()
                writer.writerow({"source_id": "known", "homepage_url": "https://example.org"})
            with endpoints.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "endpoint_id", "source_id", "label", "url", "access_method",
                        "expected_format", "content_scope", "language", "enabled",
                        "last_manual_check", "notes",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "endpoint_id": "bad",
                        "source_id": "missing",
                        "url": "https://example.org/news",
                        "access_method": "http_get",
                        "expected_format": "html",
                        "enabled": "true",
                    }
                )
            with self.assertRaises(ConfigurationError):
                load_registry(sources, endpoints)


if __name__ == "__main__":
    unittest.main()
