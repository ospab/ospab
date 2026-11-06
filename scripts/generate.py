import json
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape

USER = os.environ.get("PROFILE_USER", "ospab")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")

SKIP_LANGS = {"Makefile", "HTML", "CSS", "SCSS", "Shell", "PowerShell", "Batchfile", "Dockerfile", "CMake", "Nix"}

THEMES = {
    "dark": {"bg": "#0d1117", "fg": "#c9d1d9", "muted": "#8b949e", "line": "#30363d"},
    "light": {"bg": "#ffffff", "fg": "#24292f", "muted": "#57606a", "line": "#d0d7de"},
}
FONT = "font-family:'Segoe UI',Ubuntu,'Helvetica Neue',sans-serif"


def gql(query, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "User-Agent": "profile-stats"},
    )
    with urllib.request.urlopen(req) as r:
        body = json.load(r)
    if "errors" in body:
        sys.exit(json.dumps(body["errors"], indent=2))
    return body["data"]


def fetch():
    repos, cursor = [], None
    while True:
        data = gql(
            """
            query($login:String!, $cursor:String) {
              user(login:$login) {
                createdAt
                followers { totalCount }
                repositories(first:100, after:$cursor, ownerAffiliations:OWNER, isFork:false) {
                  pageInfo { hasNextPage endCursor }
                  nodes {
                    stargazerCount
                    languages(first:10, orderBy:{field:SIZE, direction:DESC}) {
                      edges { size node { name color } }
                    }
                  }
                }
              }
            }""",
            {"login": USER, "cursor": cursor},
        )
        user = data["user"]
        page = user["repositories"]
        repos += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    now = datetime.now(timezone.utc)
    year = gql(
        """
        query($login:String!, $from:DateTime!, $to:DateTime!) {
          user(login:$login) {
            contributionsCollection(from:$from, to:$to) {
              totalCommitContributions
              restrictedContributionsCount
              totalPullRequestContributions
              totalIssueContributions
              contributionCalendar {
                totalContributions
                weeks { contributionDays { date contributionCount } }
              }
            }
          }
        }""",
        {
            "login": USER,
            "from": (now - timedelta(days=365)).isoformat(),
            "to": now.isoformat(),
        },
    )["user"]["contributionsCollection"]
    return user, repos, year


def svg(width, height, theme, body):
    t = THEMES[theme]
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" style="{FONT}">'
        f'<rect width="{width}" height="{height}" rx="6" fill="{t["bg"]}"/>{body}</svg>'
    )


def stats_card(user, repos, year, theme):
    t = THEMES[theme]
    commits = year["totalCommitContributions"]
    rows = [
        ("Contributions, last 12 months", year["contributionCalendar"]["totalContributions"]),
        ("Commits, last 12 months", commits),
        ("Pull requests", year["totalPullRequestContributions"]),
        ("Repositories", len(repos)),
        ("Stars", sum(r["stargazerCount"] for r in repos)),
        ("On GitHub since", user["createdAt"][:4]),
    ]
    body = ""
    for i, (label, value) in enumerate(rows):
        y = 34 + i * 26
        body += (
            f'<text x="24" y="{y}" font-size="13" fill="{t["muted"]}">{escape(label)}</text>'
            f'<text x="356" y="{y}" font-size="13" font-weight="600" fill="{t["fg"]}" '
            f'text-anchor="end">{value}</text>'
        )
        if i < len(rows) - 1:
            body += f'<line x1="24" x2="356" y1="{y + 9}" y2="{y + 9}" stroke="{t["line"]}"/>'
    return svg(380, 180, theme, body)


def langs_card(repos, theme):
    t = THEMES[theme]
    sizes, colors = defaultdict(int), {}
    for r in repos:
        for e in r["languages"]["edges"]:
            if e["node"]["name"] in SKIP_LANGS:
                continue
            sizes[e["node"]["name"]] += e["size"]
            colors[e["node"]["name"]] = e["node"]["color"] or t["muted"]
    top = sorted(sizes.items(), key=lambda x: -x[1])[:8]
    total = sum(s for _, s in top) or 1

    body, x = '<clipPath id="bar"><rect x="24" y="22" width="332" height="8" rx="4"/></clipPath><g clip-path="url(#bar)">', 24.0
    for name, size in top:
        w = 332 * size / total
        body += f'<rect x="{x:.2f}" y="22" width="{w:.2f}" height="8" fill="{colors[name]}"/>'
        x += w
    body += "</g>"
    for i, (name, size) in enumerate(top):
        cx, cy = 24 + (i % 2) * 170, 58 + (i // 2) * 28
        body += (
            f'<circle cx="{cx + 5}" cy="{cy - 4}" r="5" fill="{colors[name]}"/>'
            f'<text x="{cx + 16}" y="{cy}" font-size="13" fill="{t["fg"]}">{escape(name)}</text>'
            f'<text x="{cx + 156}" y="{cy}" font-size="12" fill="{t["muted"]}" '
            f'text-anchor="end">{100 * size / total:.1f}%</text>'
        )
    return svg(380, 180, theme, body)


def activity_card(year, theme):
    t = THEMES[theme]
    weeks = year["contributionCalendar"]["weeks"]
    counts = [sum(d["contributionCount"] for d in w["contributionDays"]) for w in weeks]
    peak = max(counts) or 1
    width, height, left, top, bottom = 780, 170, 24, 38, 138
    step = (width - 2 * left) / len(counts)
    body = ""
    for frac in (0.5, 1.0):
        y = bottom - (bottom - top) * frac
        body += f'<line x1="{left}" x2="{width - left}" y1="{y:.1f}" y2="{y:.1f}" stroke="{t["line"]}" stroke-dasharray="2 4"/>'
    body += f'<line x1="{left}" x2="{width - left}" y1="{bottom}" y2="{bottom}" stroke="{t["line"]}"/>'
    for i, c in enumerate(counts):
        h = (bottom - top) * c / peak
        if c:
            body += (
                f'<rect x="{left + i * step + 1:.2f}" y="{bottom - h:.2f}" width="{step - 2:.2f}" '
                f'height="{h:.2f}" rx="1" fill="{t["fg"]}" opacity="{0.35 + 0.65 * c / peak:.2f}"/>'
            )
    last_month = None
    for i, w in enumerate(weeks):
        d = datetime.fromisoformat(w["contributionDays"][0]["date"])
        if d.month != last_month and i > 0 and d.day <= 7:
            body += f'<text x="{left + i * step:.1f}" y="{bottom + 18}" font-size="11" fill="{t["muted"]}">{d.strftime("%b")}</text>'
        last_month = d.month
    body += (
        f'<text x="{left}" y="22" font-size="11" fill="{t["muted"]}">Weekly contributions, last 12 months</text>'
        f'<text x="{width - left}" y="22" font-size="11" fill="{t["muted"]}" text-anchor="end">peak {peak}</text>'
    )
    return svg(width, height, theme, body)


def main():
    if not TOKEN:
        sys.exit("GH_TOKEN or GITHUB_TOKEN is required")
    user, repos, year = fetch()
    os.makedirs(OUT, exist_ok=True)
    for theme in THEMES:
        for name, content in (
            ("stats", stats_card(user, repos, year, theme)),
            ("languages", langs_card(repos, theme)),
            ("activity", activity_card(year, theme)),
        ):
            with open(os.path.join(OUT, f"{name}-{theme}.svg"), "w", encoding="utf-8") as f:
                f.write(content)


if __name__ == "__main__":
    main()
