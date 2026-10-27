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
        query = urllib.parse.urlencode({
            "type": "public",
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
