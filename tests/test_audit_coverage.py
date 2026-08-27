import unittest

from scripts.audit_coverage import CoverageTarget, audit_coverage
from scripts.probe_sources import Endpoint


def endpoint(source_id: str, enabled: bool = True) -> Endpoint:
    return Endpoint(
        endpoint_id=f"{source_id}_news",
        source_id=source_id,
        label="Actualités",
        url=f"https://example.org/{source_id}",
        access_method="http_get",
        expected_format="html",
        content_scope="actualités",
        language="fr",
        enabled=enabled,
        last_manual_check="2026-08-27",
        notes="",
    )


def target(*source_ids: str) -> CoverageTarget:
    return CoverageTarget(
        target_id="core",
        label="Socle",
        scope="test",
        required_source_ids=source_ids,
        reference_url="https://example.org/reference",
        enforced=True,
        notes="",
    )


class CoverageAuditTests(unittest.TestCase):
    def test_complete_target_and_outside_source(self):
        sources = {"one": {}, "two": {}, "context": {}}
        audit = audit_coverage(
            sources,
            [endpoint("one"), endpoint("two")],
            [target("one", "two")],
        )
        self.assertEqual(audit["summary"]["complete_targets"], 1)
        self.assertEqual(audit["registered_outside_current_targets"], ["context"])

    def test_distinguishes_missing_source_and_missing_endpoint(self):
        sources = {"one": {}, "two": {}}
        audit = audit_coverage(
            sources,
            [endpoint("one")],
            [target("one", "two", "three")],
        )
        result = audit["targets"][0]
        self.assertFalse(result["complete"])
        self.assertEqual(result["missing_source_ids"], ["three"])
        self.assertEqual(result["without_enabled_endpoint_source_ids"], ["two"])
        self.assertEqual(audit["summary"]["enforced_incomplete_targets"], 1)

    def test_disabled_endpoint_does_not_count(self):
        audit = audit_coverage(
            {"one": {}}, [endpoint("one", enabled=False)], [target("one")]
        )
        result = audit["targets"][0]
        self.assertEqual(result["with_enabled_endpoint_count"], 0)
        self.assertFalse(result["complete"])


if __name__ == "__main__":
    unittest.main()
