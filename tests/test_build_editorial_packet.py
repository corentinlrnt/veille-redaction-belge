import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_editorial_packet import (
    build_packet,
    render_prompt,
    validate_profile,
    write_outputs,
)


PROFILE = {
    "schema_version": 2,
    "profile_id": "test",
    "mission": "Transformer un radar en briefing.",
    "input_contract": {
        "window_hours": 36,
        "future_window_hours": 36,
        "recent_items_per_source": 1,
        "primary_items_per_source": 2,
        "source_lead_classes": ["public_body", "civil_society"],
    },
    "editorial_outputs": [],
    "angle_engines": [{"id": f"angle-{value}"} for value in range(8)],
    "originality_tests": ["Absent d'un simple tour de presse."],
    "hard_rules": [],
    "output_contract": {},
}


def radar() -> dict[str, object]:
    return {
        "generated_at": "2026-09-09T06:00:00Z",
        "summary": {
            "collected_items": 100,
            "selected_items": 1,
            "excluded_items": 4,
        },
        "items": [
            {
                "source_id": "public-source",
                "source_name": "Source publique",
                "source_class": "public_body",
                "official_status": "official_public",
                "access_model": "",
                "title": "Une mesure entre en vigueur",
                "url": "https://example.org/measure",
                "summary": "Résumé fourni par la source.",
                "published_at": "2026-09-09T05:00:00Z",
                "first_seen_at": "2026-09-09T05:30:00Z",
                "language": "fr",
                "geography": "Belgique",
                "score": 42,
                "section_id": "politics",
                "section_label": "Politiques publiques",
                "score_reasons": ["décision publique"],
                "related_items": [
                    {
                        "source_id": "media",
                        "source_name": "Média",
                        "title": "La mesure expliquée",
                        "url": "https://example.org/article",
                    }
                ],
            }
        ],
    }


def collected() -> dict[str, object]:
    return {
        "items": [
            {
                "item_id": "radar-item",
                "source_id": "public-source",
                "source_name": "Source publique",
                "source_class": "public_body",
                "title": "Une mesure entre en vigueur",
                "url": "https://example.org/measure",
                "published_at": "2026-09-09T05:00:00Z",
            },
            {
                "item_id": "primary-item",
                "source_id": "public-source",
                "source_name": "Source publique",
                "source_class": "public_body",
                "title": "Une donnée publique passée sous le radar",
                "url": "https://example.org/primary",
                "published_at": "2026-09-09T04:30:00Z",
            },
            {
                "item_id": "recent-item",
                "source_id": "media",
                "source_name": "Média",
                "source_class": "news_media",
                "title": "Une information récente hors radar",
                "url": "https://example.org/recent",
                "published_at": "2026-09-09T05:45:00Z",
            },
            {
                "item_id": "old-item",
                "source_id": "public-source",
                "source_name": "Source publique",
                "source_class": "public_body",
                "title": "Une ancienne donnée publique",
                "url": "https://example.org/old",
                "published_at": "2026-09-01T05:45:00Z",
            },
            {
                "item_id": "future-primary-item",
                "source_id": "future-public-source",
                "source_name": "Autre source publique",
                "source_class": "public_body",
                "title": "Une publication publique antidatée dans le futur",
                "url": "https://example.org/future-primary",
                "published_at": "2026-09-10T05:45:00Z",
            },
        ]
    }


class ProfileTests(unittest.TestCase):
    def test_requires_eight_angle_engines(self):
        invalid = {**PROFILE, "angle_engines": []}
        with self.assertRaisesRegex(ValueError, "huit moteurs"):
            validate_profile(invalid)

    def test_requires_primary_source_classes(self):
        invalid = {
            **PROFILE,
            "input_contract": {
                **PROFILE["input_contract"],
                "source_lead_classes": [],
            },
        }
        with self.assertRaisesRegex(ValueError, "sources primaires"):
            validate_profile(invalid)


class PacketTests(unittest.TestCase):
    def test_packet_keeps_provenance_but_removes_lexical_score(self):
        packet = build_packet(radar(), PROFILE)
        candidate = packet["candidates"][0]
        self.assertEqual(candidate["source"]["url"], "https://example.org/measure")
        self.assertEqual(
            candidate["lexically_related_sources"][0]["publisher"], "Média"
        )
        self.assertNotIn('"score":', json.dumps(packet))
        self.assertIn("score lexical", packet["input_limitations"][1])

    def test_broadens_radar_with_recent_source_diversity(self):
        packet = build_packet(radar(), PROFILE, collected())
        urls = {value["source"]["url"] for value in packet["candidates"]}
        self.assertEqual(
            urls,
            {
                "https://example.org/measure",
                "https://example.org/primary",
                "https://example.org/recent",
                "https://example.org/future-primary",
            },
        )
        by_url = {value["source"]["url"]: value for value in packet["candidates"]}
        self.assertTrue(by_url["https://example.org/measure"]["radar_selected"])
        self.assertFalse(by_url["https://example.org/recent"]["radar_selected"])
        self.assertEqual(packet["input_summary"]["recent_items_in_window"], 4)

    def test_primary_source_path_uses_same_past_36_hour_window(self):
        packet = build_packet(radar(), PROFILE, collected())
        by_url = {value["source"]["url"]: value for value in packet["candidates"]}
        self.assertTrue(
            by_url["https://example.org/measure"]["primary_source_candidate"]
        )
        self.assertTrue(
            by_url["https://example.org/primary"]["primary_source_candidate"]
        )
        self.assertFalse(
            by_url["https://example.org/future-primary"][
                "primary_source_candidate"
            ]
        )
        self.assertNotIn("https://example.org/old", by_url)
        self.assertEqual(packet["input_summary"]["primary_source_candidates"], 2)
        self.assertEqual(
            packet["input_summary"]["source_mix"]["primary_sources"],
            {"public_body": 2},
        )

    def test_prompt_contains_packet_once_and_no_placeholder(self):
        packet = build_packet(radar(), PROFILE)
        prompt = render_prompt("Avant\n{{EDITORIAL_PACKET_JSON}}\nAprès", packet)
        self.assertNotIn("{{EDITORIAL_PACKET_JSON}}", prompt)
        self.assertEqual(prompt.count('"candidate_id": "candidate-001"'), 1)

    def test_write_outputs_creates_machine_and_model_inputs(self):
        packet = build_packet(radar(), PROFILE)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet_path = root / "packet.json"
            prompt_path = root / "prompt.md"
            write_outputs(
                packet,
                "{{EDITORIAL_PACKET_JSON}}",
                packet_path,
                prompt_path,
            )
            self.assertEqual(json.loads(packet_path.read_text())["schema_version"], 2)
            self.assertIn("candidate-001", prompt_path.read_text())


class CanonicalFilesTests(unittest.TestCase):
    def test_profile_and_output_schema_keep_shared_enums_in_sync(self):
        root = Path(__file__).resolve().parents[1]
        profile = json.loads(
            (root / "data/editorial_profile.json").read_text(encoding="utf-8")
        )
        schema = json.loads(
            (root / "data/editorial_output_schema.json").read_text(encoding="utf-8")
        )
        validate_profile(profile)
        pitch_properties = schema["$defs"]["originalPitch"]["properties"]
        self.assertEqual(
            {value["id"] for value in profile["angle_engines"]},
            set(pitch_properties["angle_engine"]["enum"]),
        )
        self.assertEqual(
            set(profile["readiness_verdicts"]),
            set(pitch_properties["verdict"]["enum"]),
        )
        self.assertEqual(schema["properties"]["schema_version"]["const"], 2)
        self.assertNotIn("production_window", pitch_properties)
        primary_classes = schema["$defs"]["sourceLead"]["properties"]["sources"][
            "contains"
        ]["properties"]["source_class"]["enum"]
        self.assertEqual(
            set(profile["input_contract"]["source_lead_classes"]),
            set(primary_classes),
        )
        self.assertEqual(
            set(schema["required"]),
            {
                "schema_version",
                "briefing_date",
                "headline",
                "must_know",
                "original_pitches",
                "source_leads",
                "long_term_projects",
                "watchlist",
                "editorial_note",
            },
        )


if __name__ == "__main__":
    unittest.main()
