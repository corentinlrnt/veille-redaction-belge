import unittest
from datetime import datetime, timedelta, timezone

from scripts.build_briefing import (
    cluster_items,
    eligible_for_briefing,
    render_markdown,
    score_item,
)


RULES = {
    "briefing_hours": 36,
    "future_hours": 36,
    "priority_count": 12,
    "source_class_weights": {"parliament": 4, "public_body": 2},
    "scope_weights": {"décisions": 5, "actualités": 1},
    "sections": [
        {"id": "politics", "label": "Politique", "source_classes": ["parliament", "public_body"], "scopes": ["décisions"], "terms": ["gouvernement", "budget"]},
        {"id": "justice", "label": "Justice", "source_classes": ["judiciary"], "scopes": ["arrêts"], "terms": ["justice", "arrêt"]},
        {"id": "economy", "label": "Économie", "source_classes": ["statistics"], "scopes": ["statistiques"], "terms": ["emploi", "prix"]},
    ],
    "signals": [
        {"id": "decision", "label": "décision publique", "weight": 6, "terms": ["adopte", "réforme"]}
    ],
    "downrank_signals": [
        {"id": "promotion", "label": "promotion", "weight": -4, "terms": ["inscrivez-vous"]}
    ],
}


def item(**overrides):
    value = {
        "item_id": "one",
        "source_id": "source",
        "source_name": "Source",
        "source_class": "parliament",
        "official_status": "official_public",
        "content_scope": "décisions|actualités",
        "title": "Le gouvernement adopte une réforme du budget",
        "summary": "",
        "categories": [],
        "url": "https://example.org/one",
        "published_at": "2026-08-27T04:00:00Z",
        "first_seen_at": "2026-08-27T05:00:00Z",
        "observation_status": "new",
    }
    value.update(overrides)
    return value


class EligibilityTests(unittest.TestCase):
    def test_rejects_undated_bootstrap_but_accepts_new_item(self):
        now = datetime(2026, 8, 27, 6, tzinfo=timezone.utc)
        bootstrap = item(published_at=None, observation_status="bootstrap")
        new = item(published_at=None, observation_status="new")
        self.assertFalse(eligible_for_briefing(bootstrap, RULES, now))
        self.assertTrue(eligible_for_briefing(new, RULES, now))


class RankingTests(unittest.TestCase):
    def test_decision_scores_above_promotional_item(self):
        now = datetime(2026, 8, 27, 6, tzinfo=timezone.utc)
        decision = score_item(item(), RULES, now)
        promotion = score_item(item(title="Inscrivez-vous à notre événement"), RULES, now)
        self.assertGreater(decision["score"], promotion["score"])
        self.assertEqual(decision["section_id"], "politics")

    def test_clusters_near_duplicate_titles(self):
        first = {**item(), "score": 20, "related_items": []}
        second = {**item(item_id="two", source_id="other", source_name="Other", url="https://example.org/two"), "score": 18, "related_items": []}
        clusters = cluster_items([first, second])
        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(clusters[0]["related_items"]), 1)

    def test_markdown_keeps_source_link_and_warning(self):
        now = datetime(2026, 8, 27, 6, tzinfo=timezone.utc)
        scored = score_item(item(), RULES, now)
        document = render_markdown([scored], RULES, now, 1)
        self.assertIn("https://example.org/one", document)
        self.assertIn("pas des faits validés pour diffusion", document)
        self.assertIn("source publique officielle", document)

    def test_markdown_labels_party_claims(self):
        now = datetime(2026, 8, 27, 6, tzinfo=timezone.utc)
        scored = score_item(item(official_status="political_actor"), RULES, now)
        document = render_markdown([scored], RULES, now, 1)
        self.assertIn("acteur politique", document)

    def test_markdown_labels_professional_orders(self):
        now = datetime(2026, 8, 27, 6, tzinfo=timezone.utc)
        scored = score_item(item(official_status="professional_order"), RULES, now)
        document = render_markdown([scored], RULES, now, 1)
        self.assertIn("ordre professionnel", document)

    def test_markdown_labels_media_and_possible_paywall(self):
        now = datetime(2026, 8, 27, 6, tzinfo=timezone.utc)
        scored = score_item(
            item(
                source_class="news_media",
                official_status="editorial_media",
                access_model="mixed_paywall",
            ),
            RULES,
            now,
        )
        document = render_markdown([scored], RULES, now, 1)
        self.assertIn("média d'information", document)
        self.assertIn("article possiblement réservé aux abonnés", document)
        self.assertIn("aucun paywall n'est contourné", document)


if __name__ == "__main__":
    unittest.main()
