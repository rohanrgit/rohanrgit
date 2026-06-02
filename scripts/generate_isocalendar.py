#!/usr/bin/env python3
"""Generate a 3D isometric contribution calendar (isocalendar) SVG — light + dark.

Pulls the GitHub contribution calendar (via GITHUB_TOKEN — no PAT required) and
renders an isometric "city" where each day is a bar: colour encodes the activity
level, height encodes the contribution count.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import urllib.request
from pathlib import Path

USER = "rohanrgit"
API_URL = "https://api.github.com/graphql"
OUT_DIR = Path(__file__).resolve().parent.parent / "assets"

TILE_W = 15.0   # isometric tile footprint width
TILE_H = 8.0    # isometric tile footprint height (≈ TILE_W / 2 for 2:1 iso)
MIN_ELEV = 3.0  # bar height for a 1-contribution day
MAX_ELEV = 30.0 # bar height for the busiest day
MARGIN = 10.0

THEMES: dict[str, dict] = {
    "light": {"levels": ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]},
    "dark": {"levels": ["#2d333b", "#0e4429", "#006d32", "#26a641", "#39d353"]},
}


def graphql(query: str, variables: dict, token: str) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(API_URL, data=payload, headers={
        "Authorization": f"bearer {token}", "Content-Type": "application/json",
        "User-Agent": f"{USER}-isocalendar"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.load(r)
    if body.get("errors"):
        raise RuntimeError(f"GraphQL errors: {body['errors']}")
    return body["data"]


def fetch_calendar(token: str) -> tuple[list, int]:
    today = dt.datetime.now(dt.timezone.utc).date()
    start = today - dt.timedelta(days=364)
    query = """
    query($login:String!, $from:DateTime!, $to:DateTime!) {
      user(login:$login) {
        contributionsCollection(from:$from, to:$to) {
          contributionCalendar {
            totalContributions
            weeks { contributionDays { contributionCount weekday } }
          }
        }
      }
    }
    """
    cal = graphql(query, {"login": USER, "from": f"{start.isoformat()}T00:00:00Z",
                          "to": f"{today.isoformat()}T23:59:59Z"}, token)["user"]["contributionsCollection"]["contributionCalendar"]
    return cal["weeks"], cal["totalContributions"]


def shade(hex_color: str, factor: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    r, g, b = (max(0, min(255, round(v * factor))) for v in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def thresholds(counts: list[int]) -> list[int]:
    nz = sorted(c for c in counts if c > 0)
    if not nz:
        return [1, 2, 3, 4]
    pick = lambda p: nz[min(len(nz) - 1, int(len(nz) * p))]
    return [1, pick(0.5), pick(0.75), pick(0.9)]


def level(count: int, th: list[int]) -> int:
    if count <= 0:
        return 0
    for i, t in enumerate(th[1:], start=1):
        if count < t:
            return i
    return 4


def render(theme: str, weeks: list, th: list[int], maxc: int) -> str:
    levels = THEMES[theme]["levels"]
    root = math.sqrt(maxc) if maxc > 0 else 1.0
    cells = []  # (depth, [(points, fill), ...])
    min_x = min_y = 1e9
    max_x = max_y = -1e9
    for col, week in enumerate(weeks):
        for day in week["contributionDays"]:
            r = day["weekday"]
            cnt = day["contributionCount"]
            lv = level(cnt, th)
            elev = (MIN_ELEV + (math.sqrt(cnt) / root) * (MAX_ELEV - MIN_ELEV)) if cnt > 0 else 1.5
            cx = (col - r) * (TILE_W / 2)
            cy = (col + r) * (TILE_H / 2)
            color = levels[lv]
            faces = [
                # left face, right face, then top (painted last)
                (f"{cx - TILE_W / 2:.1f},{cy - elev:.1f} {cx:.1f},{cy - elev + TILE_H / 2:.1f} {cx:.1f},{cy + TILE_H / 2:.1f} {cx - TILE_W / 2:.1f},{cy:.1f}", shade(color, 0.55)),
                (f"{cx + TILE_W / 2:.1f},{cy - elev:.1f} {cx:.1f},{cy - elev + TILE_H / 2:.1f} {cx:.1f},{cy + TILE_H / 2:.1f} {cx + TILE_W / 2:.1f},{cy:.1f}", shade(color, 0.78)),
                (f"{cx:.1f},{cy - elev - TILE_H / 2:.1f} {cx + TILE_W / 2:.1f},{cy - elev:.1f} {cx:.1f},{cy - elev + TILE_H / 2:.1f} {cx - TILE_W / 2:.1f},{cy - elev:.1f}", color),
            ]
            cells.append((col + r, faces))
            min_x, max_x = min(min_x, cx - TILE_W / 2), max(max_x, cx + TILE_W / 2)
            min_y, max_y = min(min_y, cy - elev - TILE_H / 2), max(max_y, cy + TILE_H / 2)

    cells.sort(key=lambda c: c[0])
    dx, dy = MARGIN - min_x, MARGIN - min_y
    width = round(max_x - min_x + 2 * MARGIN)
    height = round(max_y - min_y + 2 * MARGIN)
    polys = "".join(f'<polygon points="{pts}" fill="{fill}"/>' for _, faces in cells for pts, fill in faces)
    return (f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
            f'xmlns="http://www.w3.org/2000/svg">\n'
            f'<g transform="translate({dx:.1f},{dy:.1f})" stroke-linejoin="round">\n{polys}\n</g>\n</svg>\n')


def main() -> None:
    token = os.environ.get("GH_TOKEN")
    if not token:
        raise SystemExit("GH_TOKEN environment variable is required.")
    weeks, total = fetch_calendar(token)
    counts = [d["contributionCount"] for w in weeks for d in w["contributionDays"]]
    maxc = max(counts) if counts else 0
    th = thresholds(counts)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for theme in THEMES:
        (OUT_DIR / f"isocal-{theme}.svg").write_text(render(theme, weeks, th, maxc), encoding="utf-8")
    print(f"total={total} weeks={len(weeks)} max_day={maxc} thresholds={th}")


if __name__ == "__main__":
    main()
