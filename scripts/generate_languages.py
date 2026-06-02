#!/usr/bin/env python3
"""Generate a "Most Used Languages" SVG card (light + dark).

Aggregates language bytes across the user's own (non-fork) repositories —
including private ones when the token has access — and renders two themed cards
with a stacked bar plus a legend.
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

USER = "rohanrgit"
API_URL = "https://api.github.com/graphql"
OUT_DIR = Path(__file__).resolve().parent.parent / "assets"
TOP_N = 6

THEMES: dict[str, dict[str, str]] = {
    "light": {"title": "#1f2328", "name": "#1f2328", "pct": "#59636e", "track": "#eaeef2"},
    "dark": {"title": "#e6edf3", "name": "#e6edf3", "pct": "#9198a1", "track": "#30363d"},
}


def graphql(query: str, variables: dict[str, object], token: str) -> dict:
    """Run a GraphQL query against the GitHub API and return its ``data`` block."""
    payload = json.dumps({"query": query, "variables": variables}).encode()
    request = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": f"{USER}-languages-card",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.load(response)
    if body.get("errors"):
        raise RuntimeError(f"GraphQL errors: {body['errors']}")
    return body["data"]


def language_totals(token: str) -> dict[str, list]:
    """Sum language byte counts across all owned, non-fork repositories."""
    query = """
    query($cursor:String) {
      viewer {
        repositories(first:100, after:$cursor, ownerAffiliations:OWNER, isFork:false) {
          pageInfo { hasNextPage endCursor }
          nodes {
            languages(first:20, orderBy:{field:SIZE, direction:DESC}) {
              edges { size node { name color } }
            }
          }
        }
      }
    }
    """
    totals: dict[str, list] = {}
    cursor: str | None = None
    while True:
        repositories = graphql(query, {"cursor": cursor}, token)["viewer"]["repositories"]
        for repo in repositories["nodes"]:
            for edge in repo["languages"]["edges"]:
                node = edge["node"]
                entry = totals.setdefault(node["name"], [0, node["color"] or "#858585"])
                entry[0] += edge["size"]
        page = repositories["pageInfo"]
        if not page["hasNextPage"]:
            return totals
        cursor = page["endCursor"]


def rank_languages(totals: dict[str, list]) -> list[dict]:
    """Return the top languages with their share of total bytes."""
    grand_total = sum(size for size, _ in totals.values()) or 1
    ranked = sorted(totals.items(), key=lambda item: item[1][0], reverse=True)
    return [
        {"name": name, "color": color, "pct": size * 100 / grand_total}
        for name, (size, color) in ranked[:TOP_N]
    ]


def render_svg(theme: str, languages: list[dict]) -> str:
    """Render one themed "Most Used Languages" card."""
    c = THEMES[theme]
    bar_x, bar_y, bar_w, bar_h = 25, 52, 430, 10

    segments = []
    offset = bar_x
    for lang in languages:
        width = bar_w * lang["pct"] / 100
        segments.append(f'<rect x="{offset:.2f}" y="{bar_y}" width="{width:.2f}" height="{bar_h}" fill="{lang["color"]}"/>')
        offset += width

    legend = []
    columns_x = (30, 250)
    label_x = (44, 264)
    for i, lang in enumerate(languages):
        column, row = i % 2, i // 2
        baseline = 92 + row * 26
        legend.append(
            f'<circle cx="{columns_x[column]}" cy="{baseline - 4}" r="5.5" '
            f'fill="{lang["color"]}" stroke="{c["track"]}" stroke-width="0.5"/>'
        )
        legend.append(
            f'<text x="{label_x[column]}" y="{baseline}" font-size="13" fill="{c["pct"]}">'
            f'<tspan fill="{c["name"]}" font-weight="600">{lang["name"]}</tspan> {lang["pct"]:.1f}%</text>'
        )

    rows = (len(languages) + 1) // 2
    height = 92 + (rows - 1) * 26 + 22
    indented_segments = "\n    ".join(segments)
    indented_legend = "\n  ".join(legend)
    return f"""<svg width="480" height="{height}" viewBox="0 0 480 {height}" xmlns="http://www.w3.org/2000/svg" font-family="'Segoe UI', Ubuntu, Helvetica, Arial, sans-serif">
  <text x="25" y="32" font-size="17" font-weight="700" fill="{c['title']}">Most Used Languages</text>
  <clipPath id="bar"><rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="{bar_h / 2}"/></clipPath>
  <rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="{bar_h / 2}" fill="{c['track']}"/>
  <g clip-path="url(#bar)">
    {indented_segments}
  </g>
  {indented_legend}
</svg>
"""


def main() -> None:
    token = os.environ.get("GH_TOKEN")
    if not token:
        raise SystemExit("GH_TOKEN environment variable is required.")
    languages = rank_languages(language_totals(token))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for theme in THEMES:
        (OUT_DIR / f"langs-{theme}.svg").write_text(render_svg(theme, languages), encoding="utf-8")
    print("  ".join(f"{lang['name']}={lang['pct']:.1f}%" for lang in languages))


if __name__ == "__main__":
    main()
