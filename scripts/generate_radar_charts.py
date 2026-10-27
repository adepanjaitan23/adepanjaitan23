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


def generate_activity_chart(username: str, updated: str, now: datetime) -> str:
    repos = fetch_public_repositories(username)
    primary_languages = {str(r.get("language")).strip() for r in repos if r.get("language")}
    total_stars = sum(int(r.get("stargazers_count") or 0) for r in repos)
    total_forks = sum(int(r.get("forks_count") or 0) for r in repos)
    cutoff = now.astimezone(timezone.utc) - timedelta(days=90)
    recently_updated = 0
    for repo in repos:
        updated_at = parse_timestamp(repo.get("updated_at"))
        if updated_at and updated_at >= cutoff:
            recently_updated += 1

    # Each signal is normalized to a transparent display target, not skill level.
    scores = [
        normalized_linear(len(repos), 20),
        normalized_linear(len(primary_languages), 8),
        normalized_linear(recently_updated, 10),
        normalized_log(total_stars, 100),
        normalized_log(total_forks, 30),
    ]
    labels = [
        ("Public repositories", str(len(repos))),
        ("Primary languages", str(len(primary_languages))),
        ("Updated in 90 days", str(recently_updated)),
        ("Stars received", str(total_stars)),
        ("Forks received", str(total_forks)),
    ]
    subtitle = f"Public GitHub activity · @{username} · normalized display scale 0–100"
    footer = "Raw counts shown at each axis. Activity indicators are not measures of technical skill."
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
