from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path


LOGIN = "Abood991B"
OUTPUT = Path(__file__).resolve().parents[1] / "assets" / "profile-metrics.svg"


def github_json(url: str, *, method: str = "GET", payload: dict | None = None) -> dict | list:
    token = os.environ.get("GH_TOKEN")
    if not token:
        raise RuntimeError("GH_TOKEN is required to generate profile metrics")

    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "Abood991B-profile-metrics",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def public_contribution_count() -> int:
    request = urllib.request.Request(
        f"https://github.com/users/{LOGIN}/contributions",
        headers={"User-Agent": "Abood991B-profile-metrics"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        html = response.read().decode("utf-8")
    match = re.search(r"([\d,]+)\s+contributions?\s+in the last year", html)
    if not match:
        raise RuntimeError("Could not read the public contribution count")
    return int(match.group(1).replace(",", ""))


def collect_metrics() -> dict[str, int]:
    repos = github_json(
        f"https://api.github.com/users/{LOGIN}/repos?per_page=100&type=owner"
    )
    return {
        "contributions": public_contribution_count(),
        "repositories": len(repos),
        "stars": sum(int(repo["stargazers_count"]) for repo in repos),
        "forks": sum(int(repo["forks_count"]) for repo in repos),
    }


def render_svg(metrics: dict[str, int]) -> str:
    items = [
        (f"{metrics['contributions']:,}", "CONTRIBUTIONS", "rolling 12 months", "#8b5cf6"),
        (f"{metrics['repositories']:,}", "PUBLIC REPOSITORIES", "projects &amp; experiments", "#38bdf8"),
        (f"{metrics['stars']:,}", "STARS EARNED", "across owned repos", "#34d399"),
        (f"{metrics['forks']:,}", "FORKS EARNED", "work reused by others", "#f59e0b"),
    ]
    cards = []
    for index, (value, label, note, color) in enumerate(items):
        x = 34 + index * 239
        cards.append(
            f"""
    <g transform="translate({x} 52)">
      <rect width="215" height="103" rx="13" fill="#0d1628" stroke="#26344d"/>
      <rect width="4" height="103" rx="2" fill="{color}"/>
      <text x="22" y="44" fill="#f8fafc" font-size="28" font-weight="780">{value}</text>
      <text x="22" y="67" fill="{color}" font-size="9.5" font-weight="750" letter-spacing="1.25">{label}</text>
      <text x="22" y="87" fill="#64748b" font-size="10.5">{note}</text>
    </g>"""
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="185" viewBox="0 0 1000 185" role="img" aria-labelledby="title desc">
  <title id="title">GitHub footprint</title>
  <desc id="desc">{metrics['contributions']} contributions visible on the profile in the last year, {metrics['repositories']} public repositories, {metrics['stars']} stars earned, and {metrics['forks']} forks earned.</desc>
  <defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#0b1220"/><stop offset="1" stop-color="#101827"/></linearGradient></defs>
  <rect width="1000" height="185" rx="20" fill="url(#bg)"/>
  <rect x=".75" y=".75" width="998.5" height="183.5" rx="19.25" fill="none" stroke="#26344d" stroke-width="1.5"/>
  <text x="34" y="31" fill="#64748b" font-family="IBM Plex Mono,Consolas,monospace" font-size="10" letter-spacing="2">GITHUB FOOTPRINT · GENERATED FROM PROFILE DATA</text>
  <g font-family="Inter,Segoe UI,Arial,sans-serif">{''.join(cards)}
  </g>
</svg>
"""


def main() -> None:
    OUTPUT.write_text(render_svg(collect_metrics()), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
