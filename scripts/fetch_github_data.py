#!/usr/bin/env python3
"""Fetch public GitHub repo data and generate static JSON datasets for the dashboard.

Stdlib only. Runs locally or in GitHub Actions with GITHUB_TOKEN.
"""
import base64
import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://api.github.com"
USER = os.environ.get("GITHUB_USER", "itsaslamopenclawdata")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
MAX_DETAIL_REPOS = int(os.environ.get("MAX_DETAIL_REPOS", "50"))
DETAIL_WINDOW_DAYS = int(os.environ.get("DETAIL_WINDOW_DAYS", "90"))
RETENTION_DAYS = 90
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")

STATUS_RULES = [(2, "ACTIVE"), (7, "RECENT"), (15, "COOLING"), (30, "STALE")]
FALLBACK_STATUS = "DORMANT"


# ---------------------------------------------------------------- pure helpers

def classify_activity(days_since_push):
    if days_since_push is None:
        return "UNKNOWN"
    for max_days, label in STATUS_RULES:
        if days_since_push <= max_days:
            return label
    return FALLBACK_STATUS


def days_between(iso_date, now):
    if not iso_date:
        return None
    dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
    return (now - dt).days


def clean_commit_message(message):
    if not message:
        return ""
    return message.splitlines()[0].strip()[:140]


def core_purpose(description, readme_text, topics):
    if description and description.strip():
        return description.strip()
    if readme_text:
        for para in readme_text.split("\n\n"):
            para = para.strip().lstrip("#").strip()
            if len(para) >= 20 and not para.startswith("!"):
                return " ".join(para.split())[:200]
    if topics:
        return "Topics: " + ", ".join(topics)
    return "Purpose not yet documented"


def top_level_paths(files, limit=3):
    dirs = []
    for f in files or []:
        parts = f.get("filename", "").split("/")
        top = parts[0] if len(parts) > 1 else "(root)"
        if top not in dirs:
            dirs.append(top)
        if len(dirs) >= limit:
            break
    return dirs


def build_repo_record(repo, commits=None, latest_files=None, readme_text=None, now=None):
    now = now or datetime.now(timezone.utc)
    dsp = days_between(repo.get("pushed_at"), now)
    latest = commits[0] if commits else None
    recent_msgs = [clean_commit_message(c.get("commit", {}).get("message", ""))
                   for c in (commits or [])[:3]]
    recent_msgs = [m for m in recent_msgs if m]
    functionality = ""
    if recent_msgs:
        functionality = recent_msgs[0]
        dirs = top_level_paths(latest_files)
        if dirs:
            functionality += f" (areas: {', '.join(dirs)})"
    return {
        "name": repo.get("name"),
        "url": repo.get("html_url"),
        "description": repo.get("description"),
        "core_purpose": core_purpose(repo.get("description"), readme_text, repo.get("topics")),
        "last_push": repo.get("pushed_at"),
        "days_since_push": dsp,
        "latest_commit": clean_commit_message((latest or {}).get("commit", {}).get("message")) if latest else "",
        "latest_commit_date": (latest or {}).get("commit", {}).get("committer", {}).get("date", "") if latest else "",
        "recent_functionality": functionality,
        "recent_commit_summary": " | ".join(recent_msgs),
        "primary_language": repo.get("language"),
        "languages": [repo.get("language")] if repo.get("language") else [],
        "topics": repo.get("topics") or [],
        "default_branch": repo.get("default_branch"),
        "visibility": repo.get("visibility", "public"),
        "stars": repo.get("stargazers_count", 0),
        "forks": repo.get("forks_count", 0),
        "open_issues": repo.get("open_issues_count", 0),
        "size": repo.get("size", 0),
        "created_at": repo.get("created_at"),
        "updated_at": repo.get("updated_at"),
        "is_fork": repo.get("fork", False),
        "is_archived": repo.get("archived", False),
        "homepage": repo.get("homepage"),
        "has_readme": bool(readme_text),
        "activity_status": classify_activity(dsp),
    }


def merge_history(history, daily_counts, today, retention_days=RETENTION_DAYS):
    history = dict(history or {})
    for date, count in daily_counts.items():
        if date == today:
            history[date] = {"commits": count}             # idempotent replace for today
        else:
            prev = history.get(date, {}).get("commits", 0)
            history[date] = {"commits": max(prev, count)}  # never inflate past days
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).date().isoformat()
    return {d: v for d, v in sorted(history.items()) if d >= cutoff}


# ------------------------------------------------------------------- network

def fetch_json(url, token=""):
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "solopreneur-github-dashboard",
        **({"Authorization": f"Bearer {token}"} if token else {}),
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_all_repos(user, token):
    repos, page = [], 1
    while True:
        batch = fetch_json(f"{API}/users/{user}/repos?per_page=100&page={page}&type=owner", token)
        if not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return repos


def fetch_latest_commits(full_name, token, limit=5):
    commits = fetch_json(f"{API}/repos/{full_name}/commits?per_page={limit}", token)
    return commits if isinstance(commits, list) else []


def fetch_commit_files(commit_url, token):
    return fetch_json(commit_url, token).get("files", [])


def fetch_readme_text(full_name, token):
    try:
        data = fetch_json(f"{API}/repos/{full_name}/readme", token)
        return base64.b64decode(data.get("content", "")).decode("utf-8", "replace")
    except Exception:
        return None


# ---------------------------------------------------------------------- main

def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    errors = []

    repos = fetch_all_repos(USER, TOKEN)
    all_sorted = sorted(repos, key=lambda r: r.get("pushed_at") or "", reverse=True)
    cutoff = now - timedelta(days=DETAIL_WINDOW_DAYS)
    detail = set()
    for r in [x for x in all_sorted if not x.get("archived")][:MAX_DETAIL_REPOS]:
        p = r.get("pushed_at")
        if p and datetime.fromisoformat(p.replace("Z", "+00:00")) >= cutoff:
            detail.add(r["full_name"])

    records, feed, daily_counts = [], [], {}
    for r in all_sorted:
        commits, files, readme = [], [], None
        if r["full_name"] in detail:
            try:
                commits = fetch_latest_commits(r["full_name"], TOKEN)
                if commits:
                    files = fetch_commit_files(commits[0]["url"], TOKEN)
                readme = fetch_readme_text(r["full_name"], TOKEN)
            except Exception as e:
                errors.append({"repo": r["full_name"], "error": str(e)[:200]})
        records.append(build_repo_record(r, commits, files, readme, now))
        for c in commits:
            cd = c.get("commit", {}).get("committer", {}).get("date", "")
            if cd and datetime.fromisoformat(cd.replace("Z", "+00:00")) >= cutoff:
                d = cd[:10]
                daily_counts[d] = daily_counts.get(d, 0) + 1
                feed.append({"repo": r["name"], "date": cd,
                             "message": clean_commit_message(c.get("commit", {}).get("message", "")),
                             "url": c.get("html_url", "")})
    feed.sort(key=lambda x: x["date"], reverse=True)

    history = {}
    hist_path = os.path.join(DATA_DIR, "history.json")
    if os.path.exists(hist_path):
        with open(hist_path, encoding="utf-8") as fh:
            history = json.load(fh)

    def dump(name, payload):
        with open(os.path.join(DATA_DIR, name), "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)

    dump("repos.json", {"generated_at": now.isoformat(), "user": USER, "repos": records})
    dump("activity.json", {"generated_at": now.isoformat(), "feed": feed[:100]})
    dump("history.json", merge_history(history, daily_counts, today))
    dump("metadata.json", {
        "generated_at": now.isoformat(), "user": USER, "repo_count": len(records),
        "archived_count": sum(1 for r in repos if r.get("archived")), "detail_repos": len(detail),
        "status": "ok" if not errors else "partial", "errors": errors[:20],
    })
    print(f"OK: {len(records)} repos ({len(detail)} with detail), "
          f"{len(feed)} feed entries, {len(errors)} errors")


if __name__ == "__main__":
    main()
