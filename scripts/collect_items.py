#!/usr/bin/env python3
"""Collecte les métadonnées des flux publics structurés du registre.

Le collecteur conserve les titres, liens, dates et courts extraits fournis dans
les flux. Il ne télécharge pas le texte intégral des pages liées.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit

if __package__:
    from .probe_sources import (
        ConfigurationError,
        Endpoint,
        FetchError,
        RobotsPolicy,
        detect_format,
        fetch_url,
        load_registry,
        local_name,
        parse_datetime,
        utc_now,
    )
else:
    from probe_sources import (  # type: ignore[no-redef]
        ConfigurationError,
        Endpoint,
        FetchError,
        RobotsPolicy,
        detect_format,
        fetch_url,
        load_registry,
        local_name,
        parse_datetime,
        utc_now,
    )


SCHEMA_VERSION = 1
GENERATOR = "veille-redaction-belge/collector-0.1.0"
COLLECTABLE_FORMATS = {"rss", "atom", "json_feed"}
DEFAULT_TIMEOUT = 20.0
DEFAULT_MAX_BYTES = 3_000_000


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if value:
            self.parts.append(value)


def clean_text(value: str | None, limit: int = 600) -> str:
    parser = TextExtractor()
    parser.feed(html.unescape(value or ""))
    text = " ".join(parser.parts).strip()
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0] + "…"


def canonical_url(value: str, base_url: str) -> str:
    absolute = urljoin(base_url, html.unescape(value.strip()))
    parsed = urlsplit(absolute)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, ""))


def direct_children(element: ET.Element, names: set[str]) -> Iterable[ET.Element]:
    return (child for child in list(element) if local_name(child.tag) in names)


def first_text(element: ET.Element, names: Iterable[str]) -> str:
    wanted = set(names)
    for child in direct_children(element, wanted):
        value = "".join(child.itertext()).strip()
        if value:
            return value
    return ""


def item_link(element: ET.Element, base_url: str) -> str:
    for child in direct_children(element, {"link"}):
        href = child.attrib.get("href", "").strip()
        rel = child.attrib.get("rel", "alternate").lower()
        candidate = href if href and rel in {"", "alternate"} else (child.text or "")
        if candidate and (url := canonical_url(candidate, base_url)):
            return url
    for name in ("guid", "id"):
        candidate = first_text(element, [name])
        if candidate and (url := canonical_url(candidate, base_url)):
            return url
    return canonical_url(base_url, base_url)


def item_date(element: ET.Element) -> str | None:
    values = [
        first_text(
            element,
            ["pubdate", "published", "updated", "date", "issued", "created", "modified"],
        )
    ]
    for value in values:
        if parsed := parse_datetime(value):
            return parsed.isoformat().replace("+00:00", "Z")
    return None


def fingerprint(source_id: str, guid: str, url: str, title: str) -> str:
    stable = url or guid or f"{source_id}:{title.casefold()}"
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()[:24]


def parse_xml_items(
    body: bytes,
    endpoint: Endpoint,
    source: dict[str, str],
    retrieved_at: str,
) -> list[dict[str, object]]:
    root = ET.fromstring(body)
    entries = [node for node in root.iter() if local_name(node.tag) in {"item", "entry"}]
    items: list[dict[str, object]] = []
    for entry in entries:
        title = clean_text(first_text(entry, ["title"]), 300)
        if not title:
            continue
        url = item_link(entry, endpoint.url)
        guid = first_text(entry, ["guid", "id"])
        summary = clean_text(
            first_text(entry, ["description", "summary", "content", "encoded"]),
            600,
        )
        categories = sorted(
            {
                clean_text("".join(child.itertext()), 100)
                for child in direct_children(entry, {"category", "subject"})
                if clean_text("".join(child.itertext()), 100)
            }
        )
        items.append(
            {
                "item_id": fingerprint(endpoint.source_id, guid, url, title),
                "source_id": endpoint.source_id,
                "source_name": source["name"],
                "source_class": source["source_class"],
                "institution_level": source["institution_level"],
                "geography": source["geography"],
                "official_status": source["official_status"],
                "endpoint_id": endpoint.endpoint_id,
                "endpoint_label": endpoint.label,
                "content_scope": endpoint.content_scope,
                "language": endpoint.language,
                "title": title,
                "url": url,
                "summary": summary,
                "published_at": item_date(entry),
                "retrieved_at": retrieved_at,
                "categories": categories,
            }
        )
    return items


def parse_json_feed_items(
    body: bytes,
    endpoint: Endpoint,
    source: dict[str, str],
    retrieved_at: str,
) -> list[dict[str, object]]:
    document = json.loads(body.decode("utf-8"))
    entries = document.get("items", []) if isinstance(document, dict) else []
    items: list[dict[str, object]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        title = clean_text(str(entry.get("title", "")), 300)
        if not title:
            continue
        url = canonical_url(str(entry.get("url") or entry.get("external_url") or endpoint.url), endpoint.url)
        raw_date = str(entry.get("date_published") or entry.get("date_modified") or "")
        parsed_date = parse_datetime(raw_date)
        summary = clean_text(str(entry.get("summary") or entry.get("content_text") or entry.get("content_html") or ""), 600)
        tags = entry.get("tags", [])
        categories = [clean_text(str(tag), 100) for tag in tags] if isinstance(tags, list) else []
        guid = str(entry.get("id", ""))
        items.append(
            {
                "item_id": fingerprint(endpoint.source_id, guid, url, title),
                "source_id": endpoint.source_id,
                "source_name": source["name"],
                "source_class": source["source_class"],
                "institution_level": source["institution_level"],
                "geography": source["geography"],
                "official_status": source["official_status"],
                "endpoint_id": endpoint.endpoint_id,
                "endpoint_label": endpoint.label,
                "content_scope": endpoint.content_scope,
                "language": endpoint.language,
                "title": title,
                "url": url,
                "summary": summary,
                "published_at": parsed_date.isoformat().replace("+00:00", "Z") if parsed_date else None,
                "retrieved_at": retrieved_at,
                "categories": categories,
            }
        )
    return items


@dataclass
class CollectionResult:
    endpoint_id: str
    source_id: str
    status: str
    format: str = "unknown"
    item_count: int = 0
    error: str = ""
    items: list[dict[str, object]] | None = None


def collect_endpoint(
    endpoint: Endpoint,
    source: dict[str, str],
    robots: RobotsPolicy,
    timeout: float,
    max_bytes: int,
) -> CollectionResult:
    try:
        robots_status = robots.check(endpoint.url)
        if robots_status == "disallowed":
            return CollectionResult(endpoint.endpoint_id, endpoint.source_id, "blocked_by_robots", error="Interdit par robots.txt")
        response = fetch_url(endpoint.url, timeout, max_bytes)
        detected = detect_format(response.body, response.content_type)
        retrieved_at = utc_now()
        if detected in {"rss", "atom"}:
            items = parse_xml_items(response.body, endpoint, source, retrieved_at)
        elif detected == "json_feed":
            items = parse_json_feed_items(response.body, endpoint, source, retrieved_at)
        else:
            return CollectionResult(endpoint.endpoint_id, endpoint.source_id, "unsupported", detected, error=f"Format reçu: {detected}")
        return CollectionResult(endpoint.endpoint_id, endpoint.source_id, "ok", detected, len(items), items=items)
    except FetchError as exc:
        return CollectionResult(endpoint.endpoint_id, endpoint.source_id, exc.kind, error=str(exc))
    except (ET.ParseError, json.JSONDecodeError, UnicodeError) as exc:
        return CollectionResult(endpoint.endpoint_id, endpoint.source_id, "parse_error", error=str(exc))
    except Exception as exc:
        return CollectionResult(endpoint.endpoint_id, endpoint.source_id, "network_error", error=str(exc))


def load_first_seen(path: Path) -> tuple[dict[str, dict[str, object]], bool]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}, False
    entries = document.get("items", {}) if isinstance(document, dict) else {}
    if not isinstance(entries, dict):
        return {}, True
    normalized: dict[str, dict[str, object]] = {}
    for key, value in entries.items():
        if isinstance(value, dict):
            normalized[str(key)] = dict(value)
        else:
            normalized[str(key)] = {
                "first_seen_at": str(value),
                "last_seen_at": str(value),
                "seen_count": 1,
            }
    return normalized, True


def apply_first_seen(
    items: list[dict[str, object]],
    previous: dict[str, dict[str, object]],
    now: datetime,
    initialized: bool = True,
    retention_days: int = 30,
) -> dict[str, dict[str, object]]:
    now_iso = now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    retained: dict[str, dict[str, object]] = {}
    cutoff = now.astimezone(timezone.utc) - timedelta(days=retention_days)
    for item_id, value in previous.items():
        first_seen = str(value.get("first_seen_at", ""))
        last_seen = str(value.get("last_seen_at") or first_seen)
        parsed = parse_datetime(last_seen)
        if parsed and parsed >= cutoff:
            retained[item_id] = {
                "first_seen_at": first_seen,
                "last_seen_at": parsed.isoformat().replace("+00:00", "Z"),
                "seen_count": int(value.get("seen_count", 1)),
            }
    for item in items:
        item_id = str(item["item_id"])
        if item_id in retained:
            record = retained[item_id]
            status = "existing"
            record["last_seen_at"] = now_iso
            record["seen_count"] = int(record.get("seen_count", 1)) + 1
        else:
            status = "new" if initialized else "bootstrap"
            record = {
                "first_seen_at": now_iso,
                "last_seen_at": now_iso,
                "seen_count": 1,
            }
            retained[item_id] = record
        item["first_seen_at"] = record["first_seen_at"]
        item["observation_status"] = status
        item["seen_count"] = record["seen_count"]
    return retained


def effective_datetime(item: dict[str, object]) -> datetime | None:
    return parse_datetime(str(item.get("published_at") or item.get("first_seen_at") or ""))


def load_previous_items(path: Path) -> list[dict[str, object]]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    values = document.get("items", []) if isinstance(document, dict) else []
    if not isinstance(values, list):
        return []
    return [dict(value) for value in values if isinstance(value, dict) and value.get("item_id")]


def write_outputs(
    results: list[CollectionResult],
    items: list[dict[str, object]],
    state: dict[str, dict[str, object]],
    out_json: Path,
    out_csv: Path,
    out_summary: Path,
    state_path: Path,
) -> None:
    for path in (out_json, out_csv, out_summary, state_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    statuses = Counter(result.status for result in results)
    source_count = len({str(item["source_id"]) for item in items})
    generated_at = utc_now()
    summary = {
        "configured_feeds": len(results),
        "successful_feeds": statuses.get("ok", 0),
        "failed_feeds": len(results) - statuses.get("ok", 0),
        "collected_items": len(items),
        "contributing_sources": source_count,
        "by_status": dict(sorted(statuses.items())),
    }
    document = {
        "schema_version": SCHEMA_VERSION,
        "generator": GENERATOR,
        "generated_at": generated_at,
        "summary": summary,
        "feeds": [
            {
                "endpoint_id": result.endpoint_id,
                "source_id": result.source_id,
                "status": result.status,
                "format": result.format,
                "item_count": result.item_count,
                "error": result.error,
            }
            for result in results
        ],
        "items": items,
    }
    out_json.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fields = [
        "item_id", "source_id", "source_name", "source_class", "institution_level",
        "geography", "official_status", "endpoint_id", "endpoint_label", "content_scope",
        "language", "title", "url", "summary", "published_at", "first_seen_at",
        "retrieved_at", "categories", "observation_status", "seen_count",
    ]
    with out_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for item in items:
            row = dict(item)
            row["categories"] = " | ".join(str(value) for value in item.get("categories", []))
            writer.writerow(row)
    state_path.write_text(
        json.dumps({"schema_version": 2, "updated_at": generated_at, "items": state}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Collecte des contenus structurés",
        "",
        f"Généré le `{generated_at}` par `{GENERATOR}`.",
        "",
        f"- Flux configurés : **{summary['configured_feeds']}**",
        f"- Flux collectés : **{summary['successful_feeds']}**",
        f"- Flux en erreur : **{summary['failed_feeds']}**",
        f"- Éléments conservés : **{summary['collected_items']}**",
        f"- Sources contributrices : **{summary['contributing_sources']}**",
        "",
        "| Source | Flux | Statut | Format | Éléments | Erreur |",
        "| --- | --- | --- | --- | ---: | --- |",
    ]
    for result in sorted(results, key=lambda value: (value.source_id, value.endpoint_id)):
        lines.append(
            f"| `{result.source_id}` | `{result.endpoint_id}` | `{result.status}` | `{result.format}` | {result.item_count} | {result.error.replace('|', '\\|') or '—'} |"
        )
    out_summary.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, default=Path("data/sources.csv"))
    parser.add_argument("--endpoints", type=Path, default=Path("data/endpoints.csv"))
    parser.add_argument("--rules", type=Path, default=Path("data/editorial_rules.json"))
    parser.add_argument("--out-json", type=Path, default=Path("reports/items.json"))
    parser.add_argument("--out-csv", type=Path, default=Path("reports/items.csv"))
    parser.add_argument("--out-summary", type=Path, default=Path("reports/collection-summary.md"))
    parser.add_argument("--state", type=Path, default=Path("state/first-seen.json"))
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--workers", type=int, default=6)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        sources, endpoints = load_registry(args.sources, args.endpoints)
        rules = json.loads(args.rules.read_text(encoding="utf-8"))
        lookback_hours = int(rules.get("lookback_hours", 168))
    except (ConfigurationError, FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        print(f"Configuration invalide: {exc}", file=sys.stderr)
        return 2
    previous_items = load_previous_items(args.out_json)
    selected = [
        endpoint for endpoint in endpoints
        if endpoint.enabled and endpoint.expected_format in COLLECTABLE_FORMATS
    ]
    robots = RobotsPolicy(args.timeout)
    results: list[CollectionResult] = []
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 8))) as executor:
        futures = {
            executor.submit(collect_endpoint, endpoint, sources[endpoint.source_id], robots, args.timeout, args.max_bytes): endpoint
            for endpoint in selected
        }
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda value: value.endpoint_id)
    current: dict[str, dict[str, object]] = {}
    for result in results:
        for item in result.items or []:
            current.setdefault(str(item["item_id"]), item)
    now = datetime.now(timezone.utc)
    previous_state, initialized = load_first_seen(args.state)
    state = apply_first_seen(list(current.values()), previous_state, now, initialized)
    deduplicated = {
        str(item["item_id"]): {**item, "observation_status": "cached"}
        for item in previous_items
    }
    deduplicated.update(current)
    cutoff = now - timedelta(hours=lookback_hours)
    items = [item for item in deduplicated.values() if (effective_datetime(item) or now) >= cutoff]
    items.sort(key=lambda item: effective_datetime(item) or now, reverse=True)
    write_outputs(results, items, state, args.out_json, args.out_csv, args.out_summary, args.state)
    successful = sum(result.status == "ok" for result in results)
    print(f"{successful}/{len(results)} flux collectés; {len(items)} éléments conservés.")
    return 0 if successful else 4


if __name__ == "__main__":
    raise SystemExit(main())
