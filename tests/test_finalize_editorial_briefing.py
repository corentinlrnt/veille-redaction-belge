import json
import tempfile
import unittest
from pathlib import Path

from scripts.finalize_editorial_briefing import (
    ValidationError,
    build_feedback_template,
    extract_json_object,
    render_markdown,
    validate_against_schema,
    validate_editorial_invariants,
    write_outputs,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "data/editorial_output_schema.json").read_text())
FEEDBACK_SCHEMA = json.loads(
    (ROOT / "data/editorial_feedback_schema.json").read_text()
)


def source(url="https://example.org/primary", source_class="public_body"):
    return {
        "title": "Publication",
        "publisher": "Institution",
        "source_class": source_class,
        "url": url,
        "certainty": "etabli",
    }


def output():
    return {
        "schema_version": 2,
        "briefing_date": "2026-09-11",
        "headline": "Briefing de calibration",
        "must_know": [
            {
                "rank": 1,
                "title": "Décision",
                "new_fact": "Une décision est publiée.",
                "why_it_matters": "Elle produit un effet collectif.",
                "watch_today": "La mise en œuvre.",
                "certainty": "etabli",
                "sources": [source()],
            }
        ],
        "original_pitches": [],
        "source_leads": [
            {
                "title": "Signal primaire",
                "published_clue": "Une donnée nouvelle.",
                "potential_reveal": "Un écart territorial.",
                "editorial_question": "Pourquoi cet écart ?",
                "first_verification": "Obtenir le tableau.",
                "certainty": "etabli",
                "sources": [source()],
            }
        ],
        "long_term_projects": [],
        "watchlist": [],
        "editorial_note": "Première calibration.",
    }


def packet():
    return {
        "generated_at": "2026-09-11T04:00:00Z",
        "candidates": [
            {
                "primary_source_candidate": True,
                "source": {
                    "url": "https://example.org/primary",
                    "publisher": "Institution",
                },
                "lexically_related_sources": [],
            }
        ],
    }


class JsonExtractionTests(unittest.TestCase):
    def test_accepts_raw_or_fenced_json(self):
        payload = json.dumps(output())
        self.assertEqual(extract_json_object(payload)["schema_version"], 2)
        self.assertEqual(extract_json_object(f"```json\n{payload}\n```")["schema_version"], 2)

    def test_rejects_commentary_around_json(self):
        with self.assertRaises(ValidationError):
            extract_json_object("Voici le résultat: " + json.dumps(output()))


class ValidationTests(unittest.TestCase):
    def test_validates_canonical_output(self):
        validate_against_schema(output(), SCHEMA)
        summary = validate_editorial_invariants(output(), packet())
        self.assertEqual(summary["distinct_source_urls"], 1)

    def test_rejects_unknown_field(self):
        value = {**output(), "unexpected": True}
        with self.assertRaisesRegex(ValidationError, "champ non autorisé"):
            validate_against_schema(value, SCHEMA)

    def test_rejects_non_consecutive_must_know_ranks(self):
        value = output()
        value["must_know"][0]["rank"] = 2
        with self.assertRaisesRegex(ValidationError, "rangs"):
            validate_editorial_invariants(value, packet())

    def test_rejects_source_absent_from_packet(self):
        value = output()
        value["must_know"][0]["sources"] = [source("https://invented.example/news")]
        with self.assertRaisesRegex(ValidationError, "absente du paquet"):
            validate_editorial_invariants(value, packet())

    def test_source_lead_must_use_primary_path(self):
        value = packet()
        value["candidates"][0]["primary_source_candidate"] = False
        with self.assertRaisesRegex(ValidationError, "voie primaire"):
            validate_editorial_invariants(output(), value)


class RenderingTests(unittest.TestCase):
    def test_renders_and_archives_validated_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_outputs(
                output(),
                {"validation": {"schema": "passed"}},
                root / "output.json",
                root / "latest.md",
                root / "metadata.json",
                root / "archive",
                root / "feedback",
            )
            markdown = (root / "latest.md").read_text()
            self.assertIn("En deux minutes", markdown)
            self.assertIn("Repéré hors presse", markdown)
            self.assertNotIn("pret_a_lancer", markdown)
            self.assertTrue((root / "archive/2026-09-11.json").exists())
            self.assertTrue((root / "archive/2026-09-11.md").exists())
            feedback = json.loads((root / "feedback/2026-09-11.json").read_text())
            self.assertEqual(len(feedback["items"]), 2)
            self.assertIsNone(feedback["items"][0]["verdict"])

    def test_feedback_ids_are_stable_for_a_briefing_item(self):
        payload = json.dumps(output(), ensure_ascii=False, indent=2) + "\n"
        first = build_feedback_template(output(), payload)
        second = build_feedback_template(output(), payload)
        self.assertEqual(first["items"][0]["item_id"], second["items"][0]["item_id"])
        validate_against_schema(first, FEEDBACK_SCHEMA)


if __name__ == "__main__":
    unittest.main()
