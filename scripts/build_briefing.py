#!/usr/bin/env python3
"""Classe les éléments collectés et produit un briefing sourcé, sans LLM."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

if __package__:
    from .probe_sources import parse_datetime, utc_now
else:
    from probe_sources import parse_datetime, utc_now  # type: ignore[no-redef]


SCHEMA_VERSION = 1
GENERATOR = "veille-redaction-belge/briefing-0.1.0"
BRUSSELS = ZoneInfo("Europe/Brussels")
MONTHS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]
STOPWORDS = {
    "a", "au", "aux", "avec", "ce", "ces", "dans", "de", "des", "du", "en",
    "et", "la", "le", "les", "pour", "sur", "un", "une", "van", "de", "het",
    "een", "en", "voor", "met", "op", "der", "die", "das", "den", "und", "mit",
    "von", "zu", "fur",
}


def normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", plain).split())


def matching_terms(text: str, terms: Iterable[str]) -> list[str]:
    normalized = normalize(text)
    padded = f" {normalized} "
    return [
        term for term in terms
        if normalize(term) and f" {normalize(term)} " in padded
    ]


def title_tokens(title: str) -> set[str]:
    return {
        token for token in normalize(title).split()
        if len(token) > 2 and token not in STOPWORDS
    }


def similarity(left: str, right: str) -> float:
    a, b = title_tokens(left), title_tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def split_scopes(item: dict[str, object]) -> list[str]:
    return [part.strip() for part in str(item.get("content_scope", "")).split("|") if part.strip()]


def effective_datetime(item: dict[str, object]) -> datetime | None:
    return parse_datetime(str(item.get("published_at") or item.get("first_seen_at") or ""))


def eligible_for_briefing(
    item: dict[str, object], rules: dict[str, object], now: datetime
) -> bool:
    earliest = now - timedelta(hours=int(rules.get("briefing_hours", 36)))
    latest = now + timedelta(hours=int(rules.get("future_hours", 36)))
    published = parse_datetime(str(item.get("published_at") or ""))
    if published:
        return earliest <= published <= latest
    first_seen = parse_datetime(str(item.get("first_seen_at") or ""))
    return bool(
        item.get("observation_status") == "new"
        and first_seen
        and earliest <= first_seen <= latest
    )


def classify(item: dict[str, object], rules: dict[str, object]) -> tuple[str, str, int]:
    searchable = " ".join(
        [
            str(item.get("title", "")),
            str(item.get("summary", "")),
            " ".join(str(value) for value in item.get("categories", [])),
        ]
    )
    source_class = str(item.get("source_class", ""))
    scopes = set(split_scopes(item))
    scores: list[tuple[int, int, dict[str, object]]] = []
    for index, section in enumerate(rules.get("sections", [])):
        score = 0
        if source_class in section.get("source_classes", []):
            score += 4
        score += 2 * len(scopes & set(section.get("scopes", [])))
        score += min(12, 2 * len(matching_terms(searchable, section.get("terms", []))))
        scores.append((score, -index, section))
    score, _, section = max(scores, key=lambda value: (value[0], value[1]))
    return str(section["id"]), str(section["label"]), score


def score_item(
    item: dict[str, object],
    rules: dict[str, object],
    now: datetime,
) -> dict[str, object]:
    scored = dict(item)
    section_id, section_label, section_strength = classify(item, rules)
    score = int(rules.get("source_class_weights", {}).get(str(item.get("source_class", "")), 1))
    reasons: list[str] = []
    if score > 1:
        reasons.append("producteur institutionnel ou collectif identifié")

    scope_weights = rules.get("scope_weights", {})
    weighted_scopes = sorted(
        ((int(scope_weights.get(scope, 0)), scope) for scope in split_scopes(item)),
        reverse=True,
    )
    for weight, scope in weighted_scopes[:2]:
        if weight:
            score += weight
            reasons.append(f"contenu de type {scope}")

    published = parse_datetime(str(item.get("published_at") or ""))
    date = effective_datetime(item)
    if published:
        hours = (now.astimezone(timezone.utc) - date).total_seconds() / 3600
        if hours < 0:
            recency = 4
            reasons.append("échéance ou publication future proche")
        elif hours <= 6:
            recency = 6
            reasons.append("publié depuis moins de 6 heures")
        elif hours <= 12:
            recency = 5
            reasons.append("publié depuis moins de 12 heures")
        elif hours <= 24:
            recency = 4
            reasons.append("publié depuis moins de 24 heures")
        elif hours <= 36:
            recency = 3
            reasons.append("publié depuis moins de 36 heures")
        else:
            recency = 1
        score += recency
    elif item.get("observation_status") == "new":
        score += 2
        reasons.append("nouvel élément d'un flux sans date fournie")

    searchable = " ".join(
        [
            str(item.get("title", "")),
            str(item.get("summary", "")),
            " ".join(str(value) for value in item.get("categories", [])),
        ]
    )
    matched_signals: list[str] = []
    for signal in rules.get("signals", []):
        if matching_terms(searchable, signal.get("terms", [])):
            score += int(signal["weight"])
            matched_signals.append(str(signal["id"]))
            reasons.append(str(signal["label"]))
    for signal in rules.get("downrank_signals", []):
        if matching_terms(searchable, signal.get("terms", [])):
            score += int(signal["weight"])
            reasons.append(str(signal["label"]))
    score += min(3, section_strength // 4)
    scored.update(
        {
            "score": score,
            "section_id": section_id,
            "section_label": section_label,
            "section_strength": section_strength,
            "matched_signals": matched_signals,
            "score_reasons": list(dict.fromkeys(reasons))[:6],
            "related_items": [],
        }
    )
    return scored


def cluster_items(items: list[dict[str, object]], threshold: float = 0.72) -> list[dict[str, object]]:
    clusters: list[dict[str, object]] = []
    for item in sorted(items, key=lambda value: int(value["score"]), reverse=True):
        match = next(
            (
                candidate for candidate in clusters
                if similarity(str(item["title"]), str(candidate["title"])) >= threshold
            ),
            None,
        )
        if match is None:
            clusters.append(item)
        else:
            match.setdefault("related_items", []).append(
                {
                    "source_id": item["source_id"],
                    "source_name": item["source_name"],
                    "title": item["title"],
                    "url": item["url"],
                }
            )
    return clusters


def select_items(items: list[dict[str, object]], rules: dict[str, object]) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    per_source: Counter[str] = Counter()
    max_items = int(rules.get("max_items", 36))
    max_per_source = int(rules.get("max_per_source", 3))
    for item in sorted(items, key=lambda value: (int(value["score"]), str(value.get("published_at", ""))), reverse=True):
        source_id = str(item["source_id"])
        if per_source[source_id] >= max_per_source:
            continue
        selected.append(item)
        per_source[source_id] += 1
        if len(selected) >= max_items:
            break
    return selected


def format_date(value: object) -> str:
    parsed = parse_datetime(str(value or ""))
    if not parsed:
        return "date non fournie par le flux"
    return parsed.astimezone(BRUSSELS).strftime("%d/%m/%Y à %H:%M")


def source_role(item: dict[str, object]) -> str:
    """Rend explicite la position du producteur cité."""
    roles = {
        "official_public": "source publique officielle",
        "political_actor": "acteur politique",
        "social_partner": "partenaire social",
        "civil_society": "organisation de la société civile",
        "social_security_actor": "organisme assureur",
    }
    return roles.get(str(item.get("official_status", "")), "producteur identifié")


def md_entry(item: dict[str, object]) -> list[str]:
    title = str(item["title"]).replace("[", "\\[").replace("]", "\\]")
    lines = [
        f"### [{title}]({item['url']})",
        "",
        f"**{item['source_name']}** · {source_role(item)} · {format_date(item.get('published_at') or item.get('first_seen_at'))} · score `{item['score']}`",
        "",
        f"**Signal éditorial :** {' ; '.join(str(value) for value in item.get('score_reasons', [])) or 'actualité récente du périmètre'}.",
    ]
    if item.get("summary"):
        lines.extend(["", f"> Extrait fourni par la source : {item['summary']}"])
    related = item.get("related_items", [])
    if related:
        links = ", ".join(f"[{value['source_name']}]({value['url']})" for value in related)
        lines.extend(["", f"Autres publications rapprochées automatiquement : {links}."])
    lines.append("")
    return lines


def render_markdown(
    selected: list[dict[str, object]],
    rules: dict[str, object],
    generated_at: datetime,
    collected_count: int,
) -> str:
    local = generated_at.astimezone(BRUSSELS)
    title_date = f"{local.day} {MONTHS_FR[local.month - 1]} {local.year}"
    priority_count = min(int(rules.get("priority_count", 12)), len(selected))
    priorities = selected[:priority_count]
    remaining = selected[priority_count:]
    lines = [
        f"# Veille rédaction belge — {title_date}",
        "",
        f"Générée à **{local.strftime('%H:%M')}** (heure de Bruxelles) à partir de **{collected_count} éléments collectés**.",
        "",
        "> Ce document propose des pistes, pas des faits validés pour diffusion. Chaque entrée renvoie à sa source. Le score est déterministe et explicable ; il ne remplace pas le jugement journalistique.",
        "",
        "## À regarder en priorité",
        "",
    ]
    if priorities:
        for item in priorities:
            lines.extend(md_entry(item))
    else:
        lines.extend(["Aucune publication n'atteint le seuil éditorial sur la période observée.", ""])
    by_section: dict[str, list[dict[str, object]]] = defaultdict(list)
    for item in remaining:
        by_section[str(item["section_id"])].append(item)
    for section in rules.get("sections", []):
        group = by_section.get(str(section["id"]), [])
        if not group:
            continue
        lines.extend([f"## {section['label']} — autres pistes", ""])
        for item in group:
            lines.extend(md_entry(item))
    lines.extend(
        [
            "## Méthode et limites",
            "",
            "- seuls les flux et adaptateurs de listes explicitement validés sont collectés ;",
            "- les titres proches sont regroupés par similarité lexicale, sans interprétation sémantique ;",
            "- un extrait est affiché uniquement lorsqu'il est fourni dans le flux source ;",
            "- l'absence d'une source dans ce briefing peut provenir d'un flux indisponible ou non encore collectable.",
            "",
        ]
    )
    return "\n".join(lines)


def html_entry(item: dict[str, object]) -> str:
    reasons = " ; ".join(str(value) for value in item.get("score_reasons", []))
    summary = f'<blockquote><strong>Extrait fourni par la source :</strong> {html.escape(str(item["summary"]))}</blockquote>' if item.get("summary") else ""
    related = item.get("related_items", [])
    related_html = ""
    if related:
        links = ", ".join(
            f'<a href="{html.escape(str(value["url"]), quote=True)}">{html.escape(str(value["source_name"]))}</a>'
            for value in related
        )
        related_html = f'<p class="related">Autres publications rapprochées : {links}.</p>'
    return (
        '<article class="item">'
        f'<div class="score">{int(item["score"])}</div>'
        f'<h3><a href="{html.escape(str(item["url"]), quote=True)}">{html.escape(str(item["title"]))}</a></h3>'
        f'<p class="meta"><strong>{html.escape(str(item["source_name"]))}</strong> · {html.escape(source_role(item))} · {html.escape(format_date(item.get("published_at") or item.get("first_seen_at")))}</p>'
        f'<p><strong>Signal éditorial :</strong> {html.escape(reasons or "actualité récente du périmètre")}.</p>'
        f'{summary}{related_html}</article>'
    )


def render_html(
    selected: list[dict[str, object]],
    rules: dict[str, object],
    generated_at: datetime,
    collected_count: int,
) -> str:
    local = generated_at.astimezone(BRUSSELS)
    title_date = f"{local.day} {MONTHS_FR[local.month - 1]} {local.year}"
    priority_count = min(int(rules.get("priority_count", 12)), len(selected))
    priorities = "".join(html_entry(item) for item in selected[:priority_count]) or "<p>Aucune publication n'atteint le seuil éditorial.</p>"
    remaining = selected[priority_count:]
    sections = []
    for section in rules.get("sections", []):
        group = [item for item in remaining if item["section_id"] == section["id"]]
        if group:
            sections.append(f'<h2>{html.escape(str(section["label"]))} — autres pistes</h2>' + "".join(html_entry(item) for item in group))
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Veille rédaction belge — {html.escape(title_date)}</title>
<style>
:root{{--ink:#17202a;--muted:#5f6b76;--paper:#f4f6f8;--card:#fff;--accent:#b51f36;--line:#dce1e6}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}}
main{{max-width:780px;margin:auto;padding:20px 14px 56px}}header{{padding:18px 2px}}h1{{font-size:clamp(1.7rem,7vw,2.5rem);line-height:1.05;margin:.2em 0}}h2{{margin:2.2rem 0 1rem;font-size:1.35rem}}h3{{font-size:1.08rem;line-height:1.3;margin:.15rem 2.6rem .45rem 0}}a{{color:#174a7e;text-decoration-thickness:.08em}}.intro{{color:var(--muted)}}.warning{{border-left:4px solid var(--accent);padding:.7rem 1rem;background:#fff}}
.item{{position:relative;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:12px 0;box-shadow:0 2px 9px #17202a0b}}.score{{position:absolute;right:13px;top:13px;background:var(--accent);color:white;border-radius:999px;min-width:2rem;height:2rem;display:grid;place-items:center;font-weight:700}}.meta,.related{{color:var(--muted);font-size:.9rem}}blockquote{{margin:1rem 0 0;padding:.7rem 1rem;border-left:3px solid var(--line);background:#f8fafb}}footer{{color:var(--muted);font-size:.88rem;margin-top:2rem;border-top:1px solid var(--line);padding-top:1rem}}
</style></head><body><main><header><p class="intro">Briefing automatisé · {local.strftime('%H:%M')} · {collected_count} éléments collectés</p><h1>Veille rédaction belge<br>{html.escape(title_date)}</h1></header>
<p class="warning">Pistes de traitement, pas faits validés pour diffusion. Chaque entrée conserve son lien source et un score explicable.</p>
<h2>À regarder en priorité</h2>{priorities}{''.join(sections)}
<footer>Collecte limitée aux flux et adaptateurs de listes validés. Aucun texte intégral n'est archivé. Généré par {GENERATOR}.</footer>
</main></body></html>"""


def write_outputs(
    selected: list[dict[str, object]],
    rules: dict[str, object],
    generated_at: datetime,
    collected_count: int,
    latest_md: Path,
    archive_dir: Path,
    latest_html: Path,
    html_archive_dir: Path,
    out_json: Path,
) -> None:
    local_date = generated_at.astimezone(BRUSSELS).date().isoformat()
    archive_md = archive_dir / f"{local_date}.md"
    archive_html = html_archive_dir / f"{local_date}.html"
    for path in (latest_md, archive_md, latest_html, archive_html, out_json):
        path.parent.mkdir(parents=True, exist_ok=True)
    markdown = render_markdown(selected, rules, generated_at, collected_count)
    page = render_html(selected, rules, generated_at, collected_count)
    latest_md.write_text(markdown, encoding="utf-8")
    archive_md.write_text(markdown, encoding="utf-8")
    latest_html.write_text(page, encoding="utf-8")
    archive_html.write_text(page, encoding="utf-8")
    document = {
        "schema_version": SCHEMA_VERSION,
        "generator": GENERATOR,
        "generated_at": generated_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "summary": {
            "collected_items": collected_count,
            "selected_items": len(selected),
            "minimum_score": int(rules.get("minimum_score", 7)),
            "by_section": dict(Counter(str(item["section_id"]) for item in selected)),
        },
        "items": selected,
    }
    out_json.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--items", type=Path, default=Path("reports/items.json"))
    parser.add_argument("--rules", type=Path, default=Path("data/editorial_rules.json"))
    parser.add_argument("--latest-md", type=Path, default=Path("briefings/latest.md"))
    parser.add_argument("--archive-dir", type=Path, default=Path("briefings/archive"))
    parser.add_argument("--latest-html", type=Path, default=Path("docs/index.html"))
    parser.add_argument("--html-archive-dir", type=Path, default=Path("docs/briefings"))
    parser.add_argument("--out-json", type=Path, default=Path("reports/briefing.json"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        collection = json.loads(args.items.read_text(encoding="utf-8"))
        rules = json.loads(args.rules.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"Entrée invalide: {exc}", file=sys.stderr)
        return 2
    now = datetime.now(timezone.utc)
    candidates = []
    for item in collection.get("items", []):
        if eligible_for_briefing(item, rules, now):
            scored = score_item(item, rules, now)
            if int(scored["score"]) >= int(rules.get("minimum_score", 7)):
                candidates.append(scored)
    selected = select_items(cluster_items(candidates), rules)
    write_outputs(
        selected, rules, now, len(collection.get("items", [])), args.latest_md,
        args.archive_dir, args.latest_html, args.html_archive_dir, args.out_json,
    )
    print(f"{len(selected)} pistes retenues sur {len(collection.get('items', []))} éléments collectés.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
