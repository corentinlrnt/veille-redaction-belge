#!/usr/bin/env python3
"""Valide, trace et rend lisible une sortie éditoriale produite par un modèle.

Le modèle reste interchangeable : il peut écrire sa réponse dans un fichier ou
être appelé par une commande qui lit le prompt sur l'entrée standard et renvoie
du JSON sur la sortie standard. Aucun fournisseur, secret ou SDK n'est imposé
au dépôt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo


GENERATOR = "veille-redaction-belge/editorial-finalizer-0.1.0"
BRUSSELS_TZ = ZoneInfo("Europe/Brussels")


class ValidationError(ValueError):
    """Erreur de contrat destinée à être lisible dans un journal CI."""


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValidationError(f"{path} doit contenir un objet JSON")
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_json_object(text: str) -> dict[str, Any]:
    candidate = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", candidate, re.DOTALL)
    if fenced:
        candidate = fenced.group(1)
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            f"réponse du modèle invalide à la ligne {exc.lineno}, colonne {exc.colno}: {exc.msg}"
        ) from exc
    if not isinstance(value, dict):
        raise ValidationError("la réponse du modèle doit être un objet JSON")
    return value


def schema_type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    raise ValidationError(f"type JSON Schema non pris en charge: {expected}")


def resolve_ref(root: dict[str, Any], reference: str) -> dict[str, Any]:
    if not reference.startswith("#/"):
        raise ValidationError(f"référence externe non prise en charge: {reference}")
    value: Any = root
    for part in reference[2:].split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(value, dict) or key not in value:
            raise ValidationError(f"référence de schéma introuvable: {reference}")
        value = value[key]
    if not isinstance(value, dict):
        raise ValidationError(f"référence de schéma invalide: {reference}")
    return value


def validate_schema_node(
    value: Any,
    schema: dict[str, Any],
    root: dict[str, Any],
    path: str = "$",
) -> None:
    if "$ref" in schema:
        validate_schema_node(value, resolve_ref(root, str(schema["$ref"])), root, path)
        return

    if "const" in schema and value != schema["const"]:
        raise ValidationError(f"{path}: valeur attendue {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValidationError(f"{path}: valeur hors liste autorisée: {value!r}")

    expected = schema.get("type")
    if expected is not None:
        choices = expected if isinstance(expected, list) else [expected]
        if not any(schema_type_matches(value, str(choice)) for choice in choices):
            raise ValidationError(f"{path}: type attendu {' ou '.join(map(str, choices))}")

    if isinstance(value, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                raise ValidationError(f"{path}: champ obligatoire manquant: {key}")
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            properties = {}
        if schema.get("additionalProperties") is False:
            extras = sorted(set(value) - set(properties))
            if extras:
                raise ValidationError(
                    f"{path}: champ non autorisé: {', '.join(extras)}"
                )
        for key, child in value.items():
            child_schema = properties.get(key)
            if isinstance(child_schema, dict):
                validate_schema_node(child, child_schema, root, f"{path}.{key}")

    if isinstance(value, list):
        if len(value) < int(schema.get("minItems", 0)):
            raise ValidationError(f"{path}: trop peu d'éléments")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            raise ValidationError(f"{path}: trop d'éléments")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, child in enumerate(value):
                validate_schema_node(child, item_schema, root, f"{path}[{index}]")
        contains = schema.get("contains")
        if isinstance(contains, dict):
            matches = 0
            for child in value:
                try:
                    validate_schema_node(child, contains, root, path)
                except ValidationError:
                    continue
                matches += 1
            if matches < int(schema.get("minContains", 1)):
                raise ValidationError(f"{path}: aucun élément ne satisfait 'contains'")

    if isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0)):
            raise ValidationError(f"{path}: texte trop court")
        pattern = schema.get("pattern")
        if pattern and re.search(str(pattern), value) is None:
            raise ValidationError(f"{path}: texte non conforme au motif {pattern}")
        if schema.get("format") == "uri":
            parsed = urlsplit(value)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValidationError(f"{path}: URL HTTP(S) invalide")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ValidationError(f"{path}: valeur inférieure au minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValidationError(f"{path}: valeur supérieure au maximum")


def validate_against_schema(output: dict[str, Any], schema: dict[str, Any]) -> None:
    validate_schema_node(output, schema, schema)


def iter_source_references(output: dict[str, Any]) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            sources = value.get("sources")
            if isinstance(sources, list):
                references.extend(item for item in sources if isinstance(item, dict))
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(output)
    return references


def packet_sources(packet: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], set[str]]:
    sources: dict[str, dict[str, Any]] = {}
    primary_urls: set[str] = set()
    for candidate in packet.get("candidates", []):
        if not isinstance(candidate, dict):
            continue
        source = candidate.get("source")
        if isinstance(source, dict) and source.get("url"):
            url = str(source["url"])
            sources[url] = source
            if candidate.get("primary_source_candidate") is True:
                primary_urls.add(url)
        for related in candidate.get("lexically_related_sources", []):
            if isinstance(related, dict) and related.get("url"):
                sources[str(related["url"])] = related
    return sources, primary_urls


def validate_editorial_invariants(
    output: dict[str, Any],
    packet: dict[str, Any],
    allow_external_sources: bool = False,
) -> dict[str, int]:
    known_sources, primary_urls = packet_sources(packet)
    references = iter_source_references(output)
    unknown = sorted(
        {
            str(source.get("url", ""))
            for source in references
            if str(source.get("url", "")) not in known_sources
        }
    )
    if unknown and not allow_external_sources:
        raise ValidationError(
            "source absente du paquet éditorial: " + ", ".join(unknown)
        )

    ranks = [item.get("rank") for item in output.get("must_know", [])]
    if ranks != list(range(1, len(ranks) + 1)):
        raise ValidationError("$.must_know: les rangs doivent être consécutifs à partir de 1")

    generated_at = str(packet.get("generated_at") or "")
    try:
        packet_date = datetime.fromisoformat(
            generated_at.replace("Z", "+00:00")
        ).astimezone(BRUSSELS_TZ).date().isoformat()
    except ValueError:
        packet_date = ""
    if packet_date and output.get("briefing_date") != packet_date:
        raise ValidationError(
            f"$.briefing_date: {packet_date} attendu pour ce paquet"
        )

    for index, lead in enumerate(output.get("source_leads", [])):
        lead_urls = {
            str(source.get("url", ""))
            for source in lead.get("sources", [])
            if isinstance(source, dict)
        }
        if not lead_urls.intersection(primary_urls):
            raise ValidationError(
                f"$.source_leads[{index}]: aucune source de la voie primaire du paquet"
            )

    return {
        "source_references": len(references),
        "distinct_source_urls": len(
            {str(source.get("url", "")) for source in references}
        ),
        "external_source_urls": len(unknown),
    }


def source_links(sources: list[dict[str, Any]]) -> str:
    links: list[str] = []
    for source in sources:
        publisher = str(source.get("publisher") or source.get("title") or "Source")
        links.append(f"[{publisher}]({source.get('url', '')})")
    return ", ".join(links)


def bullet_values(values: list[Any]) -> list[str]:
    return [f"- {value}" for value in values if str(value).strip()]


def render_markdown(output: dict[str, Any]) -> str:
    lines = [
        f"# {output['headline']}",
        "",
        f"Briefing éditorial du **{output['briefing_date']}**.",
        "",
        "## En deux minutes — les incontournables",
        "",
    ]
    for item in output["must_know"]:
        lines.extend(
            [
                f"### {item['rank']}. {item['title']}",
                "",
                str(item["new_fact"]),
                "",
                f"**Pourquoi c’est important :** {item['why_it_matters']}",
                "",
                f"**À surveiller :** {item['watch_today']}",
                "",
                f"**Sources :** {source_links(item['sources'])}",
                "",
            ]
        )

    lines.extend(["## Le pas de côté", ""])
    for item in output["original_pitches"]:
        lines.extend(
            [
                f"### {item['title']}",
                "",
                f"**{item['pitch']}**",
                "",
                f"**Question centrale :** {item['central_question']}",
                "",
                f"**Pas de côté :** {item['original_move']}",
                "",
                f"**Terrain :** {item['field_or_incarnation']}",
                "",
                f"**JT :** {item['tv_hook']}",
                "",
                f"**Radio :** {item['radio_hook']}",
                "",
                "**Premières preuves :**",
                "",
                *bullet_values(item["factual_basis"]),
                "",
                "**À vérifier :**",
                "",
                *bullet_values(item["checks_needed"]),
                "",
                f"**Sources :** {source_links(item['sources'])}",
                "",
            ]
        )

    lines.extend(["## Repéré hors presse", ""])
    for item in output["source_leads"]:
        lines.extend(
            [
                f"### {item['title']}",
                "",
                str(item["published_clue"]),
                "",
                f"**Ce que cela pourrait révéler :** {item['potential_reveal']}",
                "",
                f"**Question :** {item['editorial_question']}",
                "",
                f"**Première vérification :** {item['first_verification']}",
                "",
                f"**Sources :** {source_links(item['sources'])}",
                "",
            ]
        )

    lines.extend(["## À mettre en chantier", ""])
    for item in output["long_term_projects"]:
        lines.extend(
            [
                f"### {item['title']}",
                "",
                f"**{item['pitch']}**",
                "",
                f"**Question structurelle :** {item['structural_question']}",
                "",
                f"**Point de départ frais :** {item['fresh_starting_point']}",
                "",
                "**Pistes de recherche :**",
                "",
                *bullet_values(item["research_tracks"]),
                "",
                f"**Sources :** {source_links(item['sources'])}",
                "",
            ]
        )

    lines.extend(["## À surveiller", ""])
    for item in output["watchlist"]:
        lines.extend(
            [
                f"- **{item['signal']}** — {item['why_too_weak']} "
                f"**Déclencheur :** {item['trigger']} "
                f"**Sources :** {source_links(item['sources'])}",
                "",
            ]
        )
    if output["editorial_note"]:
        lines.extend(["## Note éditoriale", "", str(output["editorial_note"]), ""])
    return "\n".join(lines).rstrip() + "\n"


def build_feedback_template(output: dict[str, Any], payload: str) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for section in (
        "must_know",
        "original_pitches",
        "source_leads",
        "long_term_projects",
        "watchlist",
    ):
        for value in output.get(section, []):
            title = str(value.get("title") or value.get("signal") or "")
            stable = hashlib.sha256(
                f"{output['briefing_date']}|{section}|{title}".encode("utf-8")
            ).hexdigest()[:12]
            items.append(
                {
                    "item_id": f"{section}-{stable}",
                    "section": section,
                    "title": title,
                    "verdict": None,
                    "useful": None,
                    "original": None,
                    "feasible": None,
                    "source_value": None,
                    "comment": "",
                }
            )
    return {
        "schema_version": 1,
        "briefing_date": output["briefing_date"],
        "briefing_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "overall_comment": "",
        "items": items,
    }


def obtain_response(args: argparse.Namespace) -> tuple[str, str]:
    if bool(args.response) == bool(args.command):
        raise ValidationError("utiliser exactement --response ou --command")
    if args.response:
        return args.response.read_text(encoding="utf-8"), "response_file"
    prompt = args.prompt.read_text(encoding="utf-8")
    command = shlex.split(args.command)
    if not command:
        raise ValidationError("commande de modèle vide")
    try:
        completed = subprocess.run(
            command,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=args.timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValidationError("la commande du modèle a dépassé le délai") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip()[-1000:]
        raise ValidationError(
            f"la commande du modèle a échoué ({completed.returncode}): {detail}"
        )
    if len(completed.stdout.encode("utf-8")) > args.max_response_bytes:
        raise ValidationError("la réponse du modèle dépasse la taille autorisée")
    return completed.stdout, "command"


def write_outputs(
    output: dict[str, Any],
    metadata: dict[str, Any],
    output_json: Path,
    output_markdown: Path,
    metadata_path: Path,
    archive_dir: Path,
    feedback_dir: Path,
) -> None:
    for path in (output_json, output_markdown, metadata_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)
    feedback_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(output, ensure_ascii=False, indent=2) + "\n"
    markdown = render_markdown(output)
    output_json.write_text(payload, encoding="utf-8")
    output_markdown.write_text(markdown, encoding="utf-8")
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    date = str(output["briefing_date"])
    (archive_dir / f"{date}.json").write_text(payload, encoding="utf-8")
    (archive_dir / f"{date}.md").write_text(markdown, encoding="utf-8")
    feedback_path = feedback_dir / f"{date}.json"
    if not feedback_path.exists():
        feedback_path.write_text(
            json.dumps(
                build_feedback_template(output, payload),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--response", type=Path)
    parser.add_argument("--command")
    parser.add_argument("--prompt", type=Path, default=Path("reports/editorial-prompt.md"))
    parser.add_argument("--packet", type=Path, default=Path("reports/editorial-packet.json"))
    parser.add_argument("--schema", type=Path, default=Path("data/editorial_output_schema.json"))
    parser.add_argument("--output-json", type=Path, default=Path("reports/editorial-output.json"))
    parser.add_argument("--output-markdown", type=Path, default=Path("briefings/editorial/latest.md"))
    parser.add_argument("--metadata", type=Path, default=Path("reports/editorial-generation.json"))
    parser.add_argument("--archive-dir", type=Path, default=Path("briefings/editorial/archive"))
    parser.add_argument("--feedback-dir", type=Path, default=Path("calibration/feedback"))
    parser.add_argument("--provider", default="unconfigured")
    parser.add_argument("--model", default="unconfigured")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--max-response-bytes", type=int, default=500_000)
    parser.add_argument("--allow-external-sources", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        response, transport = obtain_response(args)
        output = extract_json_object(response)
        packet = load_object(args.packet)
        schema = load_object(args.schema)
        validate_against_schema(output, schema)
        source_summary = validate_editorial_invariants(
            output, packet, args.allow_external_sources
        )
        generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        metadata = {
            "schema_version": 1,
            "generator": GENERATOR,
            "generated_at": generated_at,
            "briefing_date": output["briefing_date"],
            "transport": transport,
            "provider": args.provider,
            "model": args.model,
            "inputs": {
                "prompt": {"path": str(args.prompt), "sha256": sha256_file(args.prompt)},
                "packet": {"path": str(args.packet), "sha256": sha256_file(args.packet)},
                "schema": {"path": str(args.schema), "sha256": sha256_file(args.schema)},
            },
            "validation": {
                "schema": "passed",
                "editorial_invariants": "passed",
                **source_summary,
            },
        }
        write_outputs(
            output,
            metadata,
            args.output_json,
            args.output_markdown,
            args.metadata,
            args.archive_dir,
            args.feedback_dir,
        )
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(f"Sortie éditoriale refusée: {exc}", file=sys.stderr)
        return 2
    print(
        f"Briefing éditorial du {output['briefing_date']} validé; "
        f"{source_summary['distinct_source_urls']} sources distinctes."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
