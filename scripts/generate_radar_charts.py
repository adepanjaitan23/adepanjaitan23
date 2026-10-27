#!/usr/bin/env python3
"""Generate self-assessed skills and GitHub activity radar charts as SVG.

Uses only the Python standard library. Activity scores are normalized indicators,
not measures of technical competence. Public repository metadata is fetched from
GitHub REST API and cached only for the duration of this run.
"""

from __future__ import annotations

import json
import math
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "skills.json"
OUTPUT_DIR = ROOT / "generated"
USERNAME = os.environ.get("GITHUB_USERNAME", "adepanjaitan23").strip()
TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
API_BASE = "https://api.github.com"
TIME_ZONE = ZoneInfo("Asia/Jakarta")

BG = "#0D1117"
PANEL = "#111820"
GRID = "#30363D"
TEXT = "#C9D1D9"
MUTED = "#8B949E"
BLUE = "#58A6FF"
CYAN = "#00BFFF"
PURPLE = "#A78BFA"


def api_get(url: str):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "adepanjaitan23-radar-charts",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"GitHub API returned HTTP {exc.code} for {url}: {details}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach GitHub API for {url}: {exc.reason}") from exc


def fetch_public_repositories(username: str) -> list[dict]:
    """Fetch all public repositories directly owned by the profile, excluding forks and archived repos."""
    repos: list[dict] = []
    page = 1
    while True:
        # GET /users/{username}/repos already lists public repositories.
        # The endpoint's `type` parameter accepts all, owner, or member, not public.
        query = urllib.parse.urlencode({
            "sort": "updated",
            "direction": "desc",
            "per_page": 100,
            "page": page,
        })
        data = api_get(f"{API_BASE}/users/{urllib.parse.quote(username)}/repos?{query}")
        if not isinstance(data, list):
            raise RuntimeError("GitHub API response for repositories was not a list.")
        repos.extend(data)
        if len(data) < 100:
            break
        page += 1
    return [r for r in repos if not r.get("fork", False) and not r.get("archived", False)]


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def normalized_linear(value: int, target: int) -> float:
    if target <= 0:
        return 0.0
    return clamp((value / target) * 100.0)


def normalized_log(value: int, target: int) -> float:
    if value <= 0:
        return 0.0
    return clamp((math.log1p(value) / math.log1p(target)) * 100.0)


def svg_text(x: float, y: float, content: str, *, size: int = 14,
             fill: str = TEXT, weight: str = "400", anchor: str = "middle",
             family: str = "Inter,Segoe UI,Arial,sans-serif") -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
        f'font-family="{family}" font-size="{size}" font-weight="{weight}" '
        f'fill="{fill}">{escape(content)}</text>'
    )


def point_at(cx: float, cy: float, radius: float, index: int, count: int) -> tuple[float, float]:
    angle = (-math.pi / 2) + (2 * math.pi * index / count)
    return cx + radius * math.cos(angle), cy + radius * math.sin(angle)


def build_radar_svg(*, title: str, subtitle: str, labels: list[tuple[str, str]],
                    scores: list[float], footer: str, accent: str, updated: str) -> str:
    if len(labels) != len(scores) or len(scores) < 3:
        raise ValueError("Radar charts require at least three matching labels and scores.")
    scores = [clamp(float(s)) for s in scores]

    width, height = 900, 620
    cx, cy, radius = 450.0, 318.0, 178.0
    count = len(scores)
    chunks: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">',
        f'<rect width="{width}" height="{height}" rx="18" fill="{BG}"/>',
        f'<rect x="1" y="1" width="{width-2}" height="{height-2}" rx="17" fill="none" stroke="{GRID}" stroke-width="1.5"/>',
        '<defs>',
        '<linearGradient id="areaFill" x1="0" y1="0" x2="1" y2="1">',
        f'<stop offset="0%" stop-color="{accent}" stop-opacity="0.40"/>',
        f'<stop offset="100%" stop-color="{PURPLE}" stop-opacity="0.12"/>',
        '</linearGradient>',
        '</defs>',
        svg_text(width / 2, 42, title, size=23, fill=TEXT, weight="700"),
        svg_text(width / 2, 68, subtitle, size=13, fill=MUTED),
    ]

    # Concentric scale rings and spokes.
    for level in range(1, 6):
        r = radius * level / 5
        pts = [point_at(cx, cy, r, i, count) for i in range(count)]
        point_str = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        chunks.append(f'<polygon points="{point_str}" fill="none" stroke="{GRID}" stroke-width="1"/>')
        if level < 5:
            chunks.append(svg_text(cx + 8, cy - r + 4, str(level * 20), size=9, fill="#6E7681", anchor="start"))

    for i in range(count):
        x, y = point_at(cx, cy, radius, i, count)
        chunks.append(f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{x:.1f}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')

    values = [point_at(cx, cy, radius * score / 100.0, i, count) for i, score in enumerate(scores)]
    point_str = " ".join(f"{x:.1f},{y:.1f}" for x, y in values)
    chunks.append(f'<polygon points="{point_str}" fill="url(#areaFill)" stroke="{accent}" stroke-width="3" stroke-linejoin="round"/>')

    for (x, y), score in zip(values, scores):
        chunks.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{accent}" stroke="{BG}" stroke-width="2"/>')

    label_radius = radius + 53
    for i, (line1, line2) in enumerate(labels):
        x, y = point_at(cx, cy, label_radius, i, count)
        angle = (-math.pi / 2) + (2 * math.pi * i / count)
        cosine = math.cos(angle)
        if cosine > 0.25:
            anchor = "start"
        elif cosine < -0.25:
            anchor = "end"
        else:
            anchor = "middle"
        chunks.append(svg_text(x, y, line1, size=13, fill=TEXT, weight="600", anchor=anchor))
        chunks.append(svg_text(x, y + 18, line2, size=12, fill=accent, weight="600", anchor=anchor))

    chunks.extend([
        svg_text(width / 2, 576, footer, size=11, fill=MUTED),
        svg_text(width / 2, 596, f"Updated {updated} WIB", size=10, fill="#6E7681"),
        '</svg>',
    ])
    return "\n".join(chunks)


def load_skills_config() -> dict:
    if not CONFIG_PATH.exists():
        raise RuntimeError(f"Skills configuration not found: {CONFIG_PATH}")
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    skills = config.get("skills", [])
    if len(skills) < 3:
        raise RuntimeError("config/skills.json must contain at least three skills.")
    for item in skills:
        if not isinstance(item.get("label"), str) or not item["label"].strip():
            raise RuntimeError("Every skill needs a non-empty label.")
        score = item.get("score")
        if not isinstance(score, (int, float)) or not 0 <= score <= 100:
            raise RuntimeError(f"Skill score for {item.get('label')} must be between 0 and 100.")
    return config


def generate_skills_chart(config: dict, updated: str) -> str:
    skills = config["skills"]
    labels = [(item["label"], f"{item['score']}/100") for item in skills]
    scores = [float(item["score"]) for item in skills]
    return build_radar_svg(
        title=config.get("title", "SKILLS RADAR"),
        subtitle=config.get("subtitle", "Self-assessed technical skills · scale 0–100"),
        labels=labels,
        scores=scores,
        footer="Self-assessed scores. Update config/skills.json when your assessment changes.",
        accent=BLUE,
        updated=updated,
    )


def fetch_public_events(username: str, *, max_pages: int = 3) -> list[dict]:
    """Fetch up to 300 recent public events exposed by GitHub's Events API."""
    events: list[dict] = []
    for page in range(1, max_pages + 1):
        query = urllib.parse.urlencode({"per_page": 100, "page": page})
        data = api_get(
            f"{API_BASE}/users/{urllib.parse.quote(username)}/events/public?{query}"
        )
        if not isinstance(data, list):
            raise RuntimeError("GitHub API response for public events was not a list.")
        events.extend(data)
        if len(data) < 100:
            break
    return events


def generate_activity_chart(username: str, updated: str, now: datetime) -> str:
    repos = fetch_public_repositories(username)
    primary_languages = {str(r.get("language")).strip() for r in repos if r.get("language")}
    cutoff = now.astimezone(timezone.utc) - timedelta(days=90)
    recently_updated = 0
    for repo in repos:
        updated_at = parse_timestamp(repo.get("updated_at"))
        if updated_at and updated_at >= cutoff:
            recently_updated += 1

    # GitHub's public Events API exposes only the latest 30 days and at most 300 events.
    # Count push events and public repository-creation events in that window.
    events_cutoff = now.astimezone(timezone.utc) - timedelta(days=30)
    public_events = fetch_public_events(username)
    push_events_30d = 0
    public_repos_created_30d: set[str] = set()
    for event in public_events:
        event_time = parse_timestamp(event.get("created_at"))
        if not event_time or event_time < events_cutoff:
            continue

        event_type = event.get("type")
        payload = event.get("payload") or {}
        if event_type == "PushEvent":
            push_events_30d += 1
        elif event_type == "CreateEvent" and payload.get("ref_type") == "repository":
            # The public events endpoint exposes public events only. Count unique repo names
            # so accidental duplicate event records do not inflate this metric.
            repo_name = (event.get("repo") or {}).get("name")
            if repo_name:
                public_repos_created_30d.add(repo_name)

    # Scores are normalized to display targets, not to other GitHub users.
    scores = [
        normalized_linear(len(repos), 20),
        normalized_linear(len(primary_languages), 8),
        normalized_linear(recently_updated, 10),
        normalized_log(push_events_30d, 50),
        normalized_log(len(public_repos_created_30d), 5),
    ]
    labels = [
        ("Public repositories", str(len(repos))),
        ("Primary languages", str(len(primary_languages))),
        ("Updated in 90 days", str(recently_updated)),
        ("Push events", f"{push_events_30d} / 30d"),
        ("Public repos created", f"{len(public_repos_created_30d)} / 30d"),
    ]
    subtitle = f"Public repository metadata + recent public events · @{username}"
    footer = "Events API history is limited to 30 days and 300 events; these are not skill measures."
    return build_radar_svg(
        title="GITHUB ACTIVITY RADAR",
        subtitle=subtitle,
        labels=labels,
        scores=scores,
        footer=footer,
        accent=CYAN,
        updated=updated,
    )


def main() -> int:
    if not USERNAME:
        print("ERROR: Set GITHUB_USERNAME.", file=sys.stderr)
        return 2
    config = load_skills_config()
    now = datetime.now(TIME_ZONE)
    updated = now.strftime("%d %b %Y, %H:%M")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    skills_svg = generate_skills_chart(config, updated)
    activity_svg = generate_activity_chart(USERNAME, updated, now)

    (OUTPUT_DIR / "skills-radar.svg").write_text(skills_svg + "\n", encoding="utf-8")
    (OUTPUT_DIR / "github-activity-radar.svg").write_text(activity_svg + "\n", encoding="utf-8")
    print(f"Generated {OUTPUT_DIR / 'skills-radar.svg'}")
    print(f"Generated {OUTPUT_DIR / 'github-activity-radar.svg'}")
    print(f"Profile: {USERNAME}; updated: {updated} Asia/Jakarta")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
