#!/usr/bin/env python3
"""Render the profile's GitHub Signal card from live contribution data.

The card is written to the repository and embedded as a local image, so the
profile never depends on a third-party renderer staying online.

Usage:
    GITHUB_TOKEN=... python scripts/generate_signal.py --output assets/signal.svg
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request

API_URL = "https://api.github.com/graphql"

QUERY = """
query ($login: String!) {
  user(login: $login) {
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
    repositories(ownerAffiliations: OWNER, privacy: PUBLIC) {
      totalCount
    }
  }
}
"""

WIDTH = 800
HEIGHT = 312
PAD = 32

BG = "#07111f"
PANEL_TOP = "#0b1730"
PANEL_BOTTOM = "#101127"
BORDER = "#1e3a5f"
ACCENT_FROM = "#22d3ee"
ACCENT_MID = "#3b82f6"
ACCENT_TO = "#8b5cf6"
TEXT = "#dceeff"
MUTED = "#6f8eaa"
LABEL = "#79e9f8"

LEVEL_COLOURS = ["#16243a", "#1d4a6b", "#1f7fa8", "#22d3ee", "#8b5cf6"]

TILES = (
    ("contributions", "CONTRIBUTIONS"),
    ("active_days", "ACTIVE DAYS"),
    ("longest_streak", "LONGEST STREAK"),
    ("repositories", "PUBLIC REPOS"),
)


def fetch(login: str, token: str) -> dict:
    payload = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    request = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "profile-signal-card",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        raise SystemExit(f"GraphQL request failed: {error.code} {error.reason}") from error
    except urllib.error.URLError as error:
        raise SystemExit(f"GraphQL request failed: {error.reason}") from error

    if "errors" in body:
        raise SystemExit(f"GraphQL returned errors: {body['errors']}")
    return body["data"]["user"]


def collect_days(user: dict) -> list[dict]:
    days: list[dict] = []
    for week_index, week in enumerate(user["contributionsCollection"]["contributionCalendar"]["weeks"]):
        for day in week["contributionDays"]:
            date = dt.date.fromisoformat(day["date"])
            days.append(
                {
                    "date": date,
                    # GitHub calendars run Sunday-first.
                    "row": (date.weekday() + 1) % 7,
                    "column": week_index,
                    "count": day["contributionCount"],
                }
            )
    return days


def streaks(days: list[dict]) -> tuple[int, int]:
    # The contribution calendar pads the current week with future dates, and
    # those zero-count days would otherwise reset the trailing streak.
    today = dt.datetime.now(dt.timezone.utc).date()
    ordered = sorted((day for day in days if day["date"] <= today), key=lambda day: day["date"])

    longest = run = 0
    for day in ordered:
        run = run + 1 if day["count"] > 0 else 0
        longest = max(longest, run)

    # An empty "today" is a grace period, not a broken streak.
    trailing = ordered
    if trailing and trailing[-1]["date"] == today and trailing[-1]["count"] == 0:
        trailing = trailing[:-1]
    current = 0
    for day in reversed(trailing):
        if day["count"] <= 0:
            break
        current += 1
    return current, longest


def thresholds(days: list[dict]) -> tuple[int, int, int]:
    counts = sorted(day["count"] for day in days if day["count"] > 0)
    if not counts:
        return 1, 2, 3

    def quantile(fraction: float) -> int:
        index = min(len(counts) - 1, int(len(counts) * fraction))
        return counts[index]

    return quantile(0.40), quantile(0.70), quantile(0.90)


def level(count: int, cuts: tuple[int, int, int]) -> int:
    if count <= 0:
        return 0
    low, mid, high = cuts
    if count <= low:
        return 1
    if count <= mid:
        return 2
    if count <= high:
        return 3
    return 4


def window_label(days: list[dict]) -> str:
    ordered = sorted(days, key=lambda day: day["date"])
    first, last = ordered[0]["date"], ordered[-1]["date"]
    return f"{first:%b %Y} &#8212; {last:%b %Y}".upper()


def render(user: dict) -> str:
    calendar = user["contributionsCollection"]["contributionCalendar"]
    days = collect_days(user)
    current_streak, longest_streak = streaks(days)
    cuts = thresholds(days)

    # The calendar pads the current week with future dates; those must not
    # count towards "days with activity".
    today = dt.datetime.now(dt.timezone.utc).date()
    active_days = sum(1 for day in days if day["date"] <= today and day["count"] > 0)

    metrics = {
        "contributions": calendar["totalContributions"],
        "active_days": active_days,
        "longest_streak": f"{longest_streak}D",
        "repositories": user["repositories"]["totalCount"],
    }

    parts: list[str] = []
    add = parts.append

    add(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="signal-title signal-desc">'
    )
    add(
        f'<title id="signal-title">GitHub activity of the last twelve months</title>'
        f'<desc id="signal-desc">{metrics["contributions"]:,} contributions on {active_days} active '
        f'days, a longest streak of {longest_streak} days, and '
        f'{metrics["repositories"]} public repositories.</desc>'
    )
    add(
        "<defs>"
        f'<linearGradient id="signal-panel" x1="0" y1="0" x2="1" y2="1">'
        f'<stop stop-color="{PANEL_TOP}"/><stop offset="1" stop-color="{PANEL_BOTTOM}"/>'
        "</linearGradient>"
        f'<linearGradient id="signal-accent" x1="0" y1="0" x2="1" y2="0">'
        f'<stop stop-color="{ACCENT_FROM}"/><stop offset=".55" stop-color="{ACCENT_MID}"/>'
        f'<stop offset="1" stop-color="{ACCENT_TO}"/></linearGradient>'
        '<filter id="signal-soft"><feGaussianBlur stdDeviation="10"/></filter>'
        "</defs>"
    )
    add(f'<rect width="{WIDTH}" height="{HEIGHT}" rx="24" fill="{BG}"/>')
    add('<g filter="url(#signal-soft)">')
    add(f'<circle cx="48" cy="16" r="105" fill="{ACCENT_FROM}" opacity=".06"/>')
    add(f'<circle cx="756" cy="300" r="118" fill="{ACCENT_TO}" opacity=".07"/>')
    add("</g>")
    add('<g font-family="Inter,Segoe UI,Arial,sans-serif">')

    add(
        f'<text x="{PAD}" y="40" fill="{LABEL}" font-size="13" font-weight="700" '
        'letter-spacing="3">GITHUB SIGNAL</text>'
    )
    add(
        f'<text x="{WIDTH - PAD}" y="40" fill="{MUTED}" font-family="Consolas,Menlo,monospace" '
        f'font-size="11" text-anchor="end">{window_label(days)}</text>'
    )

    tile_y, tile_h, gap = 56, 84, 16
    tile_w = (WIDTH - 2 * PAD - 3 * gap) // 4
    for index, (key, caption) in enumerate(TILES):
        x = PAD + index * (tile_w + gap)
        value = metrics[key]
        display = f"{value:,}" if isinstance(value, int) else value
        add(
            f'<rect x="{x}" y="{tile_y}" width="{tile_w}" height="{tile_h}" rx="14" '
            f'fill="url(#signal-panel)" stroke="{BORDER}"/>'
        )
        add(
            f'<text x="{x + 18}" y="{tile_y + 50}" fill="url(#signal-accent)" '
            f'font-size="30" font-weight="800">{display}</text>'
        )
        add(
            f'<text x="{x + 18}" y="{tile_y + 70}" fill="#8fb0cc" font-size="10.5" '
            f'font-weight="600" letter-spacing="1.4">{caption}</text>'
        )

    cell, cell_gap = 10, 3
    columns = max(day["column"] for day in days) + 1
    grid_w = columns * (cell + cell_gap) - cell_gap
    grid_x = (WIDTH - grid_w) // 2
    grid_y = 176

    add(
        f'<text x="{grid_x}" y="{grid_y - 12}" fill="{MUTED}" font-size="10" '
        'font-family="Consolas,Menlo,monospace" letter-spacing="1.2">CONTRIBUTION CALENDAR</text>'
    )

    for day in days:
        x = grid_x + day["column"] * (cell + cell_gap)
        y = grid_y + day["row"] * (cell + cell_gap)
        add(
            f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" '
            f'fill="{LEVEL_COLOURS[level(day["count"], cuts)]}"/>'
        )

    legend_y = 286
    add(
        f'<text x="{grid_x}" y="{legend_y}" fill="{MUTED}" font-size="10" '
        f'font-family="Consolas,Menlo,monospace">LESS</text>'
    )
    for index, colour in enumerate(LEVEL_COLOURS):
        x = grid_x + 40 + index * (cell + cell_gap)
        add(f'<rect x="{x}" y="{legend_y - 8}" width="{cell}" height="{cell}" rx="2" fill="{colour}"/>')
    add(
        f'<text x="{grid_x + 40 + 5 * (cell + cell_gap) + 4}" y="{legend_y}" fill="{MUTED}" '
        f'font-size="10" font-family="Consolas,Menlo,monospace">MORE</text>'
    )
    add(
        f'<text x="{grid_x + grid_w}" y="{legend_y}" fill="{MUTED}" font-size="10" '
        f'text-anchor="end" font-family="Consolas,Menlo,monospace">'
        f'CURRENT STREAK {current_streak}D</text>'
    )

    add("</g></svg>")
    return "".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="assets/signal.svg", help="destination SVG path")
    parser.add_argument("--login", default=os.environ.get("GITHUB_LOGIN"), help="GitHub login")
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"))
    args = parser.parse_args()

    if not args.login:
        raise SystemExit("A GitHub login is required via --login or GITHUB_LOGIN")
    if not args.token:
        raise SystemExit("A GitHub token is required via --token, GITHUB_TOKEN or GH_TOKEN")

    svg = render(fetch(args.login, args.token))

    destination = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    with open(destination, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(svg)

    print(f"Wrote {destination} ({len(svg)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
