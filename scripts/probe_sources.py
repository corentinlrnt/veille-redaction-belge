#!/usr/bin/env python3
"""Contrôle reproductible des accès publics répertoriés.

Le script ne conserve ni corps d'article ni communiqué intégral. Il produit
uniquement des métadonnées techniques et découvre les liens de flux annoncés
dans les pages HTML.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from threading import Lock
from typing import Iterable


SCHEMA_VERSION = 1
GENERATOR = "veille-redaction-belge/0.1.0"
USER_AGENT_TOKEN = "RTBF-news-source-audit"
USER_AGENT = f"{USER_AGENT_TOKEN}/0.1 (public-source metadata audit)"
DEFAULT_MAX_BYTES = 2_000_000
DEFAULT_TIMEOUT = 15.0
FEED_MIME_TYPES = {
    "application/atom+xml",
    "application/feed+json",
    "application/json",
    "application/rss+xml",
    "application/rdf+xml",
    "application/xml",
    "text/xml",
}
SOURCE_FIELDS = {
    "source_id",
    "name",
    "source_class",
    "institution_level",
    "geography",
    "languages",
    "homepage_url",
    "official_status",
    "last_manual_check",
    "notes",
}
ENDPOINT_FIELDS = {
    "endpoint_id",
    "source_id",
    "label",
    "url",
    "access_method",
    "expected_format",
    "content_scope",
    "language",
    "enabled",
    "last_manual_check",
    "notes",
}


class ConfigurationError(ValueError):
    """Le registre local est invalide."""


class FetchError(RuntimeError):
    """Une ressource distante n'a pas pu être récupérée."""

    def __init__(self, kind: str, message: str, http_status: int | None = None):
        super().__init__(message)
        self.kind = kind
        self.http_status = http_status


@dataclass(frozen=True)
class Endpoint:
    endpoint_id: str
    source_id: str
    label: str
    url: str
    access_method: str
    expected_format: str
    content_scope: str
    language: str
    enabled: bool
    last_manual_check: str
    notes: str


@dataclass
class FetchResponse:
    http_status: int
    final_url: str
    content_type: str
    content_encoding: str
    body: bytes
    truncated: bool


@dataclass
class ProbeResult:
    endpoint_id: str
    source_id: str
    source_name: str
    source_class: str
    institution_level: str
    label: str
    url: str
    final_url: str = ""
    access_status: str = "network_error"
    http_status: int | None = None
    content_type: str = ""
    expected_format: str = ""
    detected_format: str = "unknown"
    format_matches_expected: bool | None = None
    robots_status: str = "unknown"
    fetched_at: str = ""
    elapsed_ms: int = 0
    bytes_read: int = 0
    truncated: bool = False
    item_count: int | None = None
    latest_published_at: str | None = None
    discovered_feeds: list[str] = field(default_factory=list)
    error: str = ""


class MetadataHTMLParser(HTMLParser):
    """Extrait uniquement les flux déclarés et les dates de balises time."""

    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.feed_urls: list[str] = []
        self.time_values: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): (value or "") for key, value in attrs}
        if tag.lower() == "link":
            rel = {part.lower() for part in values.get("rel", "").split()}
            mime = values.get("type", "").split(";", 1)[0].strip().lower()
            href = values.get("href", "").strip()
            if "alternate" in rel and href and mime in FEED_MIME_TYPES:
                absolute = urllib.parse.urljoin(self.base_url, href)
                if absolute not in self.feed_urls:
                    self.feed_urls.append(absolute)
        elif tag.lower() == "time":
            value = values.get("datetime", "").strip()
            if value:
                self.time_values.append(value)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def clean_error(value: object, limit: int = 500) -> str:
    text = " ".join(str(value).split())
    return text[:limit]


def parse_bool(value: str, field_name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "oui"}:
        return True
    if normalized in {"0", "false", "no", "non"}:
        return False
    raise ConfigurationError(f"Valeur booléenne invalide pour {field_name}: {value!r}")


def validate_public_url(value: str, context: str) -> None:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigurationError(f"URL invalide pour {context}: {value!r}")
    if parsed.username or parsed.password:
        raise ConfigurationError(f"Identifiants interdits dans l'URL de {context}")


def read_csv(path: Path, required_fields: set[str]) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            actual = set(reader.fieldnames or [])
            missing = required_fields - actual
            if missing:
                raise ConfigurationError(
                    f"Colonnes manquantes dans {path}: {', '.join(sorted(missing))}"
                )
            return [
                {key: (value or "").strip() for key, value in row.items() if key}
                for row in reader
                if any((value or "").strip() for value in row.values())
            ]
    except FileNotFoundError as exc:
        raise ConfigurationError(f"Fichier introuvable: {path}") from exc


def load_registry(
    sources_path: Path, endpoints_path: Path
) -> tuple[dict[str, dict[str, str]], list[Endpoint]]:
    source_rows = read_csv(sources_path, SOURCE_FIELDS)
    endpoint_rows = read_csv(endpoints_path, ENDPOINT_FIELDS)

    sources: dict[str, dict[str, str]] = {}
    for row in source_rows:
        source_id = row["source_id"]
        if not source_id:
            raise ConfigurationError("Un source_id est vide")
        if source_id in sources:
            raise ConfigurationError(f"source_id dupliqué: {source_id}")
        validate_public_url(row["homepage_url"], source_id)
        sources[source_id] = row

    endpoints: list[Endpoint] = []
    seen_endpoint_ids: set[str] = set()
    for row in endpoint_rows:
        endpoint_id = row["endpoint_id"]
        if not endpoint_id:
            raise ConfigurationError("Un endpoint_id est vide")
        if endpoint_id in seen_endpoint_ids:
            raise ConfigurationError(f"endpoint_id dupliqué: {endpoint_id}")
        seen_endpoint_ids.add(endpoint_id)
        if row["source_id"] not in sources:
            raise ConfigurationError(
                f"Source inconnue pour {endpoint_id}: {row['source_id']}"
            )
        validate_public_url(row["url"], endpoint_id)
        if row["access_method"] != "http_get":
            raise ConfigurationError(
                f"Méthode non prise en charge pour {endpoint_id}: {row['access_method']}"
            )
        endpoints.append(
            Endpoint(
                endpoint_id=endpoint_id,
                source_id=row["source_id"],
                label=row["label"],
                url=row["url"],
                access_method=row["access_method"],
                expected_format=row["expected_format"].lower(),
                content_scope=row["content_scope"],
                language=row["language"],
                enabled=parse_bool(row["enabled"], f"{endpoint_id}.enabled"),
                last_manual_check=row["last_manual_check"],
                notes=row["notes"],
            )
        )

    if not endpoints:
        raise ConfigurationError("Aucun point d'accès n'est configuré")
    return sources, endpoints


def fetch_url(url: str, timeout: float, max_bytes: int) -> FetchResponse:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "application/atom+xml, application/rss+xml, application/feed+json, "
                "application/json, application/xml, text/xml, text/html;q=0.9, */*;q=0.2"
            ),
            # La limite de taille doit porter sur le contenu reçu. Demander une
            # réponse non compressée évite de tronquer une archive gzip avant
            # sa décompression.
            "Accept-Encoding": "identity",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(max_bytes + 1)
            truncated = len(raw) > max_bytes
            raw = raw[:max_bytes]
            encoding = response.headers.get("Content-Encoding", "").lower()
            if encoding == "gzip":
                try:
                    raw = gzip.decompress(raw)
                except (EOFError, OSError) as exc:
                    raise FetchError("parse_error", f"Réponse gzip invalide: {exc}") from exc
            content_type = response.headers.get_content_type().lower()
            return FetchResponse(
                http_status=response.status,
                final_url=response.geturl(),
                content_type=content_type,
                content_encoding=encoding,
                body=raw,
                truncated=truncated,
            )
    except urllib.error.HTTPError as exc:
        raise FetchError("http_error", f"HTTP {exc.code}: {exc.reason}", exc.code) from exc
    except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
        reason = getattr(exc, "reason", exc)
        raise FetchError("network_error", f"Connexion impossible: {reason}") from exc


class RobotsPolicy:
    """Cache les robots.txt par origine et distingue absence et indisponibilité."""

    def __init__(self, timeout: float):
        self.timeout = timeout
        self._cache: dict[str, tuple[str, urllib.robotparser.RobotFileParser | None]] = {}
        self._lock = Lock()

    def check(self, url: str) -> str:
        parsed = urllib.parse.urlsplit(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        with self._lock:
            cached = self._cache.get(origin)

        # Le téléchargement reste hors verrou : des origines différentes doivent
        # pouvoir être contrôlées en parallèle. Deux accès simultanés à la même
        # origine peuvent exceptionnellement dupliquer cette petite requête.
        if cached is None:
            robots_url = urllib.parse.urljoin(origin, "/robots.txt")
            try:
                response = fetch_url(robots_url, self.timeout, 500_000)
                text = response.body.decode("utf-8", errors="replace")
                parser = urllib.robotparser.RobotFileParser()
                parser.set_url(robots_url)
                parser.parse(text.splitlines())
                candidate = ("present", parser)
            except FetchError as exc:
                if exc.kind == "http_error" and exc.http_status == 404:
                    candidate = ("missing", None)
                else:
                    candidate = ("unknown", None)
            with self._lock:
                cached = self._cache.setdefault(origin, candidate)

        status, parser = cached
        if status != "present" or parser is None:
            return status
        return "allowed" if parser.can_fetch(USER_AGENT_TOKEN, url) else "disallowed"


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def detect_format(body: bytes, content_type: str) -> str:
    mime = content_type.split(";", 1)[0].strip().lower()
    sample = body[:4096].lstrip().lower()
    if mime == "application/feed+json":
        return "json_feed"
    if mime == "application/json" or sample.startswith((b"{", b"[")):
        return "json"
    if mime in {"text/html", "application/xhtml+xml"} or b"<html" in sample:
        return "html"
    if mime in {"application/rss+xml", "application/rdf+xml"}:
        return "rss"
    if mime == "application/atom+xml":
        return "atom"
    if mime in {"application/xml", "text/xml"} or sample.startswith(b"<?xml"):
        try:
            root = ET.fromstring(body)
        except ET.ParseError:
            return "xml"
        root_name = local_name(root.tag)
        if root_name in {"rss", "rdf"}:
            return "rss"
        if root_name == "feed":
            return "atom"
        return "xml"
    return "unknown"


def format_matches_expected(expected: str, detected: str) -> bool:
    """Compare le format reçu aux formats et adaptateurs déclarés.

    ``wp_json`` et ``html_articles`` sont des adaptateurs de collecte opt-in :
    le format de transport reste respectivement JSON et HTML.
    """

    return (
        expected in {"", "auto"}
        or detected == expected
        or (expected == "xml" and detected in {"xml", "rss", "atom"})
        or (expected == "wp_json" and detected == "json")
        or (expected == "html_articles" and detected == "html")
    )


def parse_datetime(value: str) -> datetime | None:
    candidate = value.strip()
    if not candidate:
        return None
    try:
        parsed = parsedate_to_datetime(candidate)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def newest_iso(values: Iterable[str]) -> str | None:
    parsed = [value for raw in values if (value := parse_datetime(raw)) is not None]
    if not parsed:
        return None
    return max(parsed).isoformat().replace("+00:00", "Z")


def parse_xml_metadata(body: bytes) -> tuple[int | None, str | None]:
    root = ET.fromstring(body)
    item_count = sum(1 for element in root.iter() if local_name(element.tag) in {"item", "entry"})
    dates = [
        element.text or ""
        for element in root.iter()
        if local_name(element.tag)
        in {"pubdate", "published", "updated", "date", "issued", "created"}
    ]
    return item_count, newest_iso(dates)


def parse_json_metadata(body: bytes) -> tuple[int | None, str | None]:
    data = json.loads(body.decode("utf-8"))
    if isinstance(data, list):
        entries = data
    elif isinstance(data, dict):
        candidate = data.get("items", data.get("entries", data.get("results", [])))
        entries = candidate if isinstance(candidate, list) else []
    else:
        entries = []
    date_values: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for key in ("date_published", "date_modified", "published", "updated", "date"):
            if isinstance(entry.get(key), str):
                date_values.append(entry[key])
    return len(entries), newest_iso(date_values)


def parse_html_metadata(body: bytes, base_url: str) -> tuple[list[str], str | None]:
    parser = MetadataHTMLParser(base_url)
    parser.feed(body.decode("utf-8", errors="replace"))
    return parser.feed_urls[:10], newest_iso(parser.time_values)


def probe_endpoint(
    endpoint: Endpoint,
    source: dict[str, str],
    robots: RobotsPolicy,
    timeout: float,
    max_bytes: int,
    skip_robots: bool,
) -> ProbeResult:
    result = ProbeResult(
        endpoint_id=endpoint.endpoint_id,
        source_id=endpoint.source_id,
        source_name=source["name"],
        source_class=source["source_class"],
        institution_level=source["institution_level"],
        label=endpoint.label,
        url=endpoint.url,
        expected_format=endpoint.expected_format,
    )
    started = time.monotonic()
    result.fetched_at = utc_now()
    try:
        result.robots_status = "not_checked" if skip_robots else robots.check(endpoint.url)
        if result.robots_status == "disallowed":
            result.access_status = "blocked_by_robots"
            result.error = "Accès interdit pour la sonde par robots.txt"
            return result

        response = fetch_url(endpoint.url, timeout, max_bytes)
        result.http_status = response.http_status
        result.final_url = response.final_url
        result.content_type = response.content_type
        result.bytes_read = len(response.body)
        result.truncated = response.truncated
        result.detected_format = detect_format(response.body, response.content_type)
        result.format_matches_expected = format_matches_expected(
            endpoint.expected_format, result.detected_format
        )

        if result.detected_format == "html":
            result.discovered_feeds, result.latest_published_at = parse_html_metadata(
                response.body, response.final_url
            )
        elif result.detected_format in {"rss", "atom", "xml"}:
            result.item_count, result.latest_published_at = parse_xml_metadata(response.body)
        elif result.detected_format in {"json", "json_feed"}:
            result.item_count, result.latest_published_at = parse_json_metadata(response.body)
        else:
            result.access_status = "unsupported"
            result.error = "Format non reconnu"
            return result
        result.access_status = "ok"
    except FetchError as exc:
        result.access_status = exc.kind
        result.http_status = exc.http_status
        result.error = clean_error(exc)
    except (ET.ParseError, json.JSONDecodeError, UnicodeError) as exc:
        result.access_status = "parse_error"
        result.error = clean_error(exc)
    except Exception as exc:  # filet de sécurité, visible dans le rapport
        result.access_status = "network_error"
        result.error = clean_error(exc)
    finally:
        result.elapsed_ms = round((time.monotonic() - started) * 1000)
    return result


def build_summary(results: list[ProbeResult], configured_enabled: int) -> dict[str, object]:
    statuses = Counter(result.access_status for result in results)
    formats = Counter(result.detected_format for result in results)
    robots = Counter(result.robots_status for result in results)
    return {
        "configured_enabled": configured_enabled,
        "probed": len(results),
        "ok": statuses.get("ok", 0),
        "errors": len(results) - statuses.get("ok", 0),
        "by_access_status": dict(sorted(statuses.items())),
        "by_detected_format": dict(sorted(formats.items())),
        "by_robots_status": dict(sorted(robots.items())),
        "format_mismatches": sum(
            result.format_matches_expected is False for result in results
        ),
        "discovered_feed_candidates": sum(len(result.discovered_feeds) for result in results),
    }


def result_to_csv_row(result: ProbeResult) -> dict[str, object]:
    row = asdict(result)
    row["discovered_feeds"] = " | ".join(result.discovered_feeds)
    return row


def write_reports(
    results: list[ProbeResult],
    summary: dict[str, object],
    json_path: Path,
    csv_path: Path,
    markdown_path: Path,
) -> None:
    for path in (json_path, csv_path, markdown_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    document = {
        "schema_version": SCHEMA_VERSION,
        "generator": GENERATOR,
        "generated_at": utc_now(),
        "summary": summary,
        "results": [asdict(result) for result in results],
    }
    json_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    fieldnames = list(asdict(results[0]).keys()) if results else list(asdict(ProbeResult("", "", "", "", "", "", "")).keys())
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(result_to_csv_row(result) for result in results)

    lines = [
        "# Santé des accès",
        "",
        f"Généré le `{document['generated_at']}` par `{GENERATOR}`.",
        "",
        f"- Accès configurés et actifs : **{summary['configured_enabled']}**",
        f"- Accès testés : **{summary['probed']}**",
        f"- Accès opérationnels : **{summary['ok']}**",
        f"- Accès en erreur ou bloqués : **{summary['errors']}**",
        f"- Flux candidats découverts : **{summary['discovered_feed_candidates']}**",
        "",
        "| Source | Accès | Statut | HTTP | Format attendu → reçu | Robots | Flux trouvés |",
        "| --- | --- | --- | ---: | --- | --- | ---: |",
    ]
    for result in sorted(results, key=lambda item: (item.source_name.lower(), item.label.lower())):
        lines.append(
            "| {source} | {label} | `{status}` | {http} | `{format}` | `{robots}` | {feeds} |".format(
                source=result.source_name.replace("|", "\\|"),
                label=result.label.replace("|", "\\|"),
                status=result.access_status,
                http=result.http_status if result.http_status is not None else "—",
                format=f"{result.expected_format} → {result.detected_format}",
                robots=result.robots_status,
                feeds=len(result.discovered_feeds),
            )
        )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, default=Path("data/sources.csv"))
    parser.add_argument("--endpoints", type=Path, default=Path("data/endpoints.csv"))
    parser.add_argument("--out-json", type=Path, default=Path("reports/health.json"))
    parser.add_argument("--out-csv", type=Path, default=Path("reports/access-matrix.csv"))
    parser.add_argument("--out-md", type=Path, default=Path("reports/health-summary.md"))
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--skip-robots",
        action="store_true",
        help="Réservé au diagnostic local; ne pas utiliser dans l'automatisation.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        sources, endpoints = load_registry(args.sources, args.endpoints)
    except ConfigurationError as exc:
        print(f"Configuration invalide: {exc}", file=sys.stderr)
        return 2

    enabled = [endpoint for endpoint in endpoints if endpoint.enabled]
    robots = RobotsPolicy(args.timeout)
    results: list[ProbeResult] = []
    workers = max(1, min(args.workers, 8))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                probe_endpoint,
                endpoint,
                sources[endpoint.source_id],
                robots,
                args.timeout,
                args.max_bytes,
                args.skip_robots,
            ): endpoint
            for endpoint in enabled
        }
        for future in as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda result: result.endpoint_id)
    summary = build_summary(results, len(enabled))
    write_reports(results, summary, args.out_json, args.out_csv, args.out_md)
    print(
        f"{summary['ok']}/{summary['probed']} accès opérationnels; "
        f"{summary['discovered_feed_candidates']} flux candidats découverts."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
