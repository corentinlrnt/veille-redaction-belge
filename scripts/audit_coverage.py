#!/usr/bin/env python3
"""Mesure la couverture déclarée du registre de sources.

Une cible n'est complète que si toutes les sources attendues sont enregistrées
et possèdent au moins un point d'accès actif. Ce contrôle ne préjuge ni de la
qualité éditoriale des contenus ni de la santé technique observée à l'instant T.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

if __package__:
    from .probe_sources import (
        ConfigurationError,
        Endpoint,
        load_registry,
        parse_bool,
        read_csv,
        utc_now,
        validate_public_url,
    )
else:
    from probe_sources import (  # type: ignore[no-redef]
        ConfigurationError,
        Endpoint,
        load_registry,
        parse_bool,
        read_csv,
        utc_now,
        validate_public_url,
    )


SCHEMA_VERSION = 1
GENERATOR = "veille-redaction-belge/coverage-0.1.0"
TARGET_FIELDS = {
    "target_id",
    "label",
    "scope",
    "required_source_ids",
    "reference_url",
    "enforced",
    "notes",
}


@dataclass(frozen=True)
class CoverageTarget:
    target_id: str
    label: str
    scope: str
    required_source_ids: tuple[str, ...]
    reference_url: str
    enforced: bool
    notes: str


def load_targets(path: Path) -> list[CoverageTarget]:
    rows = read_csv(path, TARGET_FIELDS)
    targets: list[CoverageTarget] = []
    seen: set[str] = set()
    for row in rows:
        target_id = row["target_id"]
        if not target_id:
            raise ConfigurationError("Un target_id est vide")
        if target_id in seen:
            raise ConfigurationError(f"target_id dupliqué: {target_id}")
        seen.add(target_id)

        required = tuple(
            source_id.strip()
            for source_id in row["required_source_ids"].split("|")
            if source_id.strip()
        )
        if not required:
            raise ConfigurationError(f"Aucune source requise pour {target_id}")
        if len(required) != len(set(required)):
            raise ConfigurationError(f"Source requise en double dans {target_id}")
        validate_public_url(row["reference_url"], f"{target_id}.reference_url")
        targets.append(
            CoverageTarget(
                target_id=target_id,
                label=row["label"],
                scope=row["scope"],
                required_source_ids=required,
                reference_url=row["reference_url"],
                enforced=parse_bool(row["enforced"], f"{target_id}.enforced"),
                notes=row["notes"],
            )
        )
    if not targets:
        raise ConfigurationError("Aucune cible de couverture n'est configurée")
    return targets


def audit_coverage(
    sources: dict[str, dict[str, str]],
    endpoints: list[Endpoint],
    targets: list[CoverageTarget],
) -> dict[str, object]:
    enabled_counts = Counter(
        endpoint.source_id for endpoint in endpoints if endpoint.enabled
    )
    required_union: set[str] = set()
    results: list[dict[str, object]] = []

    for target in targets:
        required = set(target.required_source_ids)
        required_union.update(required)
        missing = sorted(required - sources.keys())
        present = sorted(required & sources.keys())
        without_enabled_endpoint = sorted(
            source_id for source_id in present if enabled_counts[source_id] == 0
        )
        complete = not missing and not without_enabled_endpoint
        results.append(
            {
                "target_id": target.target_id,
                "label": target.label,
                "scope": target.scope,
                "enforced": target.enforced,
                "reference_url": target.reference_url,
                "notes": target.notes,
                "required_count": len(required),
                "present_count": len(present),
                "with_enabled_endpoint_count": len(present)
                - len(without_enabled_endpoint),
                "missing_source_ids": missing,
                "without_enabled_endpoint_source_ids": without_enabled_endpoint,
                "complete": complete,
            }
        )

    complete_targets = sum(bool(result["complete"]) for result in results)
    enforced_incomplete = sum(
        bool(result["enforced"]) and not bool(result["complete"])
        for result in results
    )
    return {
        "summary": {
            "registered_sources": len(sources),
            "enabled_endpoints": sum(enabled_counts.values()),
            "declared_targets": len(targets),
            "complete_targets": complete_targets,
            "incomplete_targets": len(targets) - complete_targets,
            "enforced_incomplete_targets": enforced_incomplete,
            "unique_required_sources": len(required_union),
            "registered_outside_current_targets": len(sources.keys() - required_union),
        },
        "registered_outside_current_targets": sorted(sources.keys() - required_union),
        "targets": results,
    }


def write_reports(
    audit: dict[str, object],
    json_path: Path,
    csv_path: Path,
    markdown_path: Path,
) -> None:
    for path in (json_path, csv_path, markdown_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    generated_at = utc_now()
    document = {
        "schema_version": SCHEMA_VERSION,
        "generator": GENERATOR,
        "generated_at": generated_at,
        **audit,
    }
    json_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    fieldnames = [
        "target_id",
        "label",
        "scope",
        "enforced",
        "required_count",
        "present_count",
        "with_enabled_endpoint_count",
        "complete",
        "missing_source_ids",
        "without_enabled_endpoint_source_ids",
        "reference_url",
        "notes",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for result in audit["targets"]:  # type: ignore[union-attr]
            row = dict(result)
            row["missing_source_ids"] = " | ".join(row["missing_source_ids"])
            row["without_enabled_endpoint_source_ids"] = " | ".join(
                row["without_enabled_endpoint_source_ids"]
            )
            writer.writerow(row)

    summary = audit["summary"]
    lines = [
        "# Couverture déclarée",
        "",
        f"Généré le `{generated_at}` par `{GENERATOR}`.",
        "",
        f"- Sources enregistrées : **{summary['registered_sources']}**",
        f"- Points d'accès actifs : **{summary['enabled_endpoints']}**",
        f"- Cibles complètes : **{summary['complete_targets']}/{summary['declared_targets']}**",
        f"- Sources requises distinctes : **{summary['unique_required_sources']}**",
        f"- Sources hors des cibles actuelles : **{summary['registered_outside_current_targets']}**",
        "",
        "Une cible `complète` signifie seulement que chaque producteur attendu est inscrit et possède au moins un accès actif. La sonde de santé vérifie séparément si cet accès répond réellement.",
        "",
        "| Cible | Périmètre | Requises | Présentes | Avec accès | Statut | Lacunes |",
        "| --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for result in audit["targets"]:  # type: ignore[union-attr]
        gaps = list(result["missing_source_ids"])
        gaps.extend(
            f"{source_id} (sans accès actif)"
            for source_id in result["without_enabled_endpoint_source_ids"]
        )
        lines.append(
            "| {label} | {scope} | {required} | {present} | {enabled} | `{status}` | {gaps} |".format(
                label=str(result["label"]).replace("|", "\\|"),
                scope=str(result["scope"]).replace("|", "\\|"),
                required=result["required_count"],
                present=result["present_count"],
                enabled=result["with_enabled_endpoint_count"],
                status="complete" if result["complete"] else "incomplete",
                gaps=", ".join(gaps) if gaps else "—",
            )
        )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, default=Path("data/sources.csv"))
    parser.add_argument("--endpoints", type=Path, default=Path("data/endpoints.csv"))
    parser.add_argument(
        "--targets", type=Path, default=Path("data/coverage_targets.csv")
    )
    parser.add_argument("--out-json", type=Path, default=Path("reports/coverage.json"))
    parser.add_argument(
        "--out-csv", type=Path, default=Path("reports/coverage-matrix.csv")
    )
    parser.add_argument(
        "--out-md", type=Path, default=Path("reports/coverage-summary.md")
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        sources, endpoints = load_registry(args.sources, args.endpoints)
        targets = load_targets(args.targets)
    except ConfigurationError as exc:
        print(f"Configuration invalide: {exc}", file=sys.stderr)
        return 2

    audit = audit_coverage(sources, endpoints, targets)
    write_reports(audit, args.out_json, args.out_csv, args.out_md)
    summary = audit["summary"]
    print(
        f"{summary['complete_targets']}/{summary['declared_targets']} cibles complètes; "
        f"{summary['unique_required_sources']} sources distinctes requises."
    )
    return 3 if summary["enforced_incomplete_targets"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
