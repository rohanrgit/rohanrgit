#!/usr/bin/env python3
"""Generate accurate GitHub contribution-streak SVG cards (light + dark).

Computes total contributions, current streak, and longest streak from the
GitHub GraphQL contributions calendar, then renders two themed SVGs. Unlike the
public streak-stats instance, the current streak never counts a zero-contribution
boundary day, so the figures match GitHub's own contribution graph exactly.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import urllib.request
from pathlib import Path

USER = "rohanrgit"
API_URL = "https://api.github.com/graphql"
OUT_DIR = Path(__file__).resolve().parent.parent / "assets"

THEMES: dict[str, dict[str, str]] = {
    "light": {"text": "#1f2328", "label": "#59636e", "accent": "#e8590c", "divider": "#d1d9e0"},
    "dark": {"text": "#e6edf3", "label": "#9198a1", "accent": "#ff8c42", "divider": "#30363d"},
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
            "User-Agent": f"{USER}-streak-card",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.load(response)
    if body.get("errors"):
        raise RuntimeError(f"GraphQL errors: {body['errors']}")
    return body["data"]


def account_created(token: str) -> dt.date:
    """Return the user's account creation date."""
    data = graphql("query($login:String!){user(login:$login){createdAt}}", {"login": USER}, token)
    return dt.datetime.fromisoformat(data["user"]["createdAt"].replace("Z", "+00:00")).date()


def daily_contributions(token: str) -> list[tuple[dt.date, int]]:
    """Fetch per-day contribution counts from account creation through today (UTC)."""
    query = """
    query($login:String!, $from:DateTime!, $to:DateTime!) {
      user(login:$login) {
        contributionsCollection(from:$from, to:$to) {
          contributionCalendar {
            weeks { contributionDays { date contributionCount } }
          }
        }
      }
    }
    """
    today = dt.datetime.now(dt.timezone.utc).date()
    counts: dict[dt.date, int] = {}
    window_start = account_created(token)
    while window_start <= today:
        window_end = min(window_start + dt.timedelta(days=364), today)
        data = graphql(
            query,
            {
                "login": USER,
                "from": f"{window_start.isoformat()}T00:00:00Z",
                "to": f"{window_end.isoformat()}T23:59:59Z",
            },
            token,
        )
        weeks = data["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
        for week in weeks:
            for day in week["contributionDays"]:
                date = dt.date.fromisoformat(day["date"])
                if window_start <= date <= window_end:
                    counts[date] = day["contributionCount"]
        window_start = window_end + dt.timedelta(days=1)
    return [(date, counts[date]) for date in sorted(counts)]


def compute_stats(days: list[tuple[dt.date, int]]) -> dict[str, object]:
    """Derive total, current-streak, and longest-streak figures from daily counts."""
    total = sum(count for _, count in days)

    longest = 0
    longest_start: dt.date | None = None
    longest_end: dt.date | None = None
    run = 0
    run_start: dt.date | None = None
    for date, count in days:
        if count > 0:
            run_start = date if run == 0 else run_start
            run += 1
            if run > longest:
                longest, longest_start, longest_end = run, run_start, date
        else:
            run = 0

    index = len(days) - 1
    if days and days[-1][1] == 0:  # today has no contributions yet — don't break the streak
        index -= 1
    end_index = index
    current = 0
    while index >= 0 and days[index][1] > 0:
        current += 1
        index -= 1
    current_start = days[index + 1][0] if current else None
    current_end = days[end_index][0] if current else None

    return {
        "total": total,
        "current": current,
        "current_start": current_start,
        "current_end": current_end,
        "longest": longest,
        "longest_start": longest_start,
        "longest_end": longest_end,
        "first_day": days[0][0] if days else None,
    }


def fmt_day(date: dt.date, *, with_year: bool) -> str:
    """Format a date as ``May 27`` or ``May 27, 2026``."""
    label = f"{date:%b} {date.day}"
    return f"{label}, {date.year}" if with_year else label


def fmt_range(start: dt.date | None, end: dt.date | None, today: dt.date) -> str:
    """Format a streak's date span, showing the year only when it isn't this year."""
    if start is None or end is None:
        return "—"
    with_year = today.year not in (start.year, end.year)
    return f"{fmt_day(start, with_year=with_year)} – {fmt_day(end, with_year=with_year)}"


def render_svg(theme: str, stats: dict[str, object], today: dt.date) -> str:
    """Render one themed streak card as an SVG string."""
    c = THEMES[theme]
    first_day = stats["first_day"]
    total_range = f"{fmt_day(first_day, with_year=True)} – Present" if first_day else "—"
    current_range = fmt_range(stats["current_start"], stats["current_end"], today)
    longest_range = fmt_range(stats["longest_start"], stats["longest_end"], today)
    return f"""<svg width="495" height="195" viewBox="0 0 495 195" xmlns="http://www.w3.org/2000/svg" font-family="'Segoe UI', Ubuntu, Helvetica, Arial, sans-serif">
  <line x1="165" y1="42" x2="165" y2="153" stroke="{c['divider']}" stroke-width="1"/>
  <line x1="330" y1="42" x2="330" y2="153" stroke="{c['divider']}" stroke-width="1"/>

  <text x="82.5" y="84" text-anchor="middle" font-size="30" font-weight="700" fill="{c['text']}">{stats['total']:,}</text>
  <text x="82.5" y="114" text-anchor="middle" font-size="14" font-weight="600" fill="{c['accent']}">Total Contributions</text>
  <text x="82.5" y="134" text-anchor="middle" font-size="11" fill="{c['label']}">{total_range}</text>

  <circle cx="247.5" cy="76" r="42" fill="none" stroke="{c['accent']}" stroke-width="5"/>
  <text x="247.5" y="86" text-anchor="middle" font-size="30" font-weight="700" fill="{c['text']}">{stats['current']}</text>
  <text x="247.5" y="36" text-anchor="middle" font-size="22">🔥</text>
  <text x="247.5" y="142" text-anchor="middle" font-size="14" font-weight="600" fill="{c['accent']}">Current Streak</text>
  <text x="247.5" y="162" text-anchor="middle" font-size="11" fill="{c['label']}">{current_range}</text>

  <text x="412.5" y="84" text-anchor="middle" font-size="30" font-weight="700" fill="{c['text']}">{stats['longest']}</text>
  <text x="412.5" y="114" text-anchor="middle" font-size="14" font-weight="600" fill="{c['accent']}">Longest Streak</text>
  <text x="412.5" y="134" text-anchor="middle" font-size="11" fill="{c['label']}">{longest_range}</text>
</svg>
"""


def main() -> None:
    token = os.environ.get("GH_TOKEN")
    if not token:
        raise SystemExit("GH_TOKEN environment variable is required.")
    today = dt.datetime.now(dt.timezone.utc).date()
    days = daily_contributions(token)
    stats = compute_stats(days)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for theme in THEMES:
        (OUT_DIR / f"streak-{theme}.svg").write_text(render_svg(theme, stats, today), encoding="utf-8")
    print(
        f"total={stats['total']} "
        f"current={stats['current']} ({stats['current_start']}..{stats['current_end']}) "
        f"longest={stats['longest']} ({stats['longest_start']}..{stats['longest_end']})"
    )


if __name__ == "__main__":
    main()
