# Solopreneur GitHub Command Center — Implementation Plan (V1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A static, GitHub Pages-hosted daily dashboard showing recent repos, last push, core purpose, and recent functionality — data refreshed by a scheduled GitHub Action.

**Architecture:** Python data pipeline (stdlib only) runs in GitHub Actions every 6 hours, fetches public repo + commit data via GitHub REST API with `GITHUB_TOKEN`, writes static JSON to `data/`. Vanilla HTML/CSS/JS frontend reads those JSON files client-side (no build step). Pages serves the repo root.

**Tech Stack:** Python 3.12 (stdlib `urllib`), pytest, vanilla JS, GitHub Actions, GitHub Pages. No frameworks, no Docker, no backend.

**Spec:** User's master prompt (61 sections) as amended by 2026-09-24 review: **V1 = Phases 1–4 + CSV export (§20) + README (§49) + Customize Fields (§10, marked mandatory in spec)**. Explicitly deferred to V1.5/V2: KPI cards (§15), charts (§16–18), language/activity filters (§29–30), dark mode (§33), health signals (§27), attention signal (§23), focus matrix (§58), LLM summaries (§55).

## Global Constraints

- Repo name: `solopreneur-github-dashboard`, **public** (required for free GitHub Pages; data is public-only per spec §35).
- GitHub user: `itsaslamopenclawdata` (all API calls scoped to this user, `type=owner`).
- Archived repos excluded from data by default (spec §43); forks included with an `is_fork` flag.
- Never commit secrets; `GITHUB_TOKEN` only inside Actions (spec §34).
- Activity status rules (spec §14), configurable in JS `CONFIG`: 0–2 ACTIVE, 3–7 RECENT, 8–15 COOLING, 16–30 STALE, >30 DORMANT.
- Frontend must work from static JSON only — no browser-side GitHub API calls (spec §36).
- Data refresh: every 6 hours via `schedule` + `workflow_dispatch` (spec §37); if a run fails, previous committed data must still render (spec §48 — satisfied trivially since data is committed, not overwritten on failure).
- History retention: 90 days (spec §40).
- All filters work together and CSV export respects them (spec §28, §20).
- Preferences in `localStorage` (spec §31).
- Python: stdlib only for the pipeline (`requirements.txt` lists just `pytest` for dev).

---

### Task 1: Repo Scaffold

**Files:**
- Create: `D:/solopreneur-github-dashboard/.gitignore`
- Create: `D:/solopreneur-github-dashboard/LICENSE` (MIT, copyright 2026 Aslam Shaik)
- Create: `D:/solopreneur-github-dashboard/.gitignore`

**Interfaces:**
- Produces: git repo at `D:/solopreneur-github-dashboard` on branch `main`.

- [ ] **Step 1: Create directory and git init**

```bash
mkdir -p D:/solopreneur-github-dashboard && cd D:/solopreneur-github-dashboard
git init -b main
```

- [ ] **Step 2: Write `.gitignore`**

```
__pycache__/
*.pyc
.pytest_cache/
.env
.venv/
```

- [ ] **Step 3: Write MIT LICENSE** (standard MIT text, copyright 2026 Aslam Shaik)

- [ ] **Step 4: Initial commit**

```bash
git add .gitignore LICENSE
git commit -m "chore: scaffold solopreneur-github-dashboard"
```

---

### Task 2: Data Pipeline — Pure Functions (TDD)

**Files:**
- Test: `tests/test_fetch_github_data.py`
- Create: `scripts/fetch_github_data.py` (module skeleton with pure functions only)

**Interfaces:**
- Consumes: none.
- Produces (exact signatures used by Task 3 and the tests):
  - `classify_activity(days_since_push: int | None) -> str` → one of `ACTIVE/RECENT/COOLING/STALE/DORMANT/UNKNOWN`
  - `days_between(iso_date: str | None, now: datetime) -> int | None`
  - `clean_commit_message(message: str | None) -> str`
  - `core_purpose(description: str | None, readme_text: str | None, topics: list | None) -> str`
  - `top_level_paths(files: list | None, limit: int = 3) -> list[str]`
  - `build_repo_record(repo: dict, commits: list | None, latest_files: list | None, readme_text: str | None, now: datetime) -> dict`
  - `merge_history(history: dict, daily_counts: dict, today: str, retention_days: int = 90) -> dict`
  - Constants: `STATUS_RULES`, `FALLBACK_STATUS`, `RETENTION_DAYS`, `API`, `USER`, `TOKEN`, `MAX_DETAIL_REPOS`, `DETAIL_WINDOW_DAYS`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for fetch_github_data pure functions. No network access."""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fetch_github_data as f

NOW = datetime(2026, 9, 24, 4, 0, 0, tzinfo=timezone.utc)


def repo_fixture(**over):
    base = {
        "name": "demo", "full_name": "me/demo", "html_url": "https://github.com/me/demo",
        "description": "A demo repo", "pushed_at": "2026-09-23T02:00:31Z",
        "language": "Python", "topics": ["ai"], "default_branch": "main",
        "visibility": "public", "stargazers_count": 3, "forks_count": 1,
        "open_issues_count": 2, "size": 120, "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-09-23T02:00:31Z", "fork": False, "archived": False,
        "homepage": None,
    }
    base.update(over)
    return base


def commit_fixture(msg="feat: add intake validation", date="2026-09-24T01:00:00Z"):
    return {"html_url": "https://github.com/me/demo/commit/abc",
            "commit": {"message": msg,
                       "committer": {"date": date}}}


class TestClassifyActivity:
    def test_boundaries(self):
        assert f.classify_activity(0) == "ACTIVE"
        assert f.classify_activity(2) == "ACTIVE"
        assert f.classify_activity(3) == "RECENT"
        assert f.classify_activity(7) == "RECENT"
        assert f.classify_activity(8) == "COOLING"
        assert f.classify_activity(15) == "COOLING"
        assert f.classify_activity(16) == "STALE"
        assert f.classify_activity(30) == "STALE"
        assert f.classify_activity(31) == "DORMANT"
        assert f.classify_activity(None) == "UNKNOWN"


class TestDaysBetween:
    def test_counts_whole_days(self):
        assert f.days_between("2026-09-23T04:00:00Z", NOW) == 0
        assert f.days_between("2026-09-20T04:00:00Z", NOW) == 4

    def test_none_stays_none(self):
        assert f.days_between(None, NOW) is None


class TestCleanCommitMessage:
    def test_first_line_only(self):
        assert f.clean_commit_message("fix api.py\n\nlong body here") == "fix api.py"

    def test_truncates_long_lines(self):
        assert len(f.clean_commit_message("x" * 500)) == 140

    def test_empty(self):
        assert f.clean_commit_message(None) == ""


class TestCorePurpose:
    def test_description_wins(self):
        assert f.core_purpose("Desc", "README para", ["t"]) == "Desc"

    def test_readme_fallback(self):
        rd = "# Demo\n\nThis project automates beekeeping operations end to end."
        assert f.core_purpose(None, rd, ["honey"]) == "This project automates beekeeping operations end to end."

    def test_topics_fallback(self):
        assert f.core_purpose(None, None, ["honey", "bees"]) == "Topics: honey, bees"

    def test_undocumented(self):
        assert f.core_purpose(None, None, []) == "Purpose not yet documented"


class TestTopLevelPaths:
    def test_dirs_deduped_and_limited(self):
        files = [{"filename": "api/a.py"}, {"filename": "api/b.py"},
                 {"filename": "web/c.js"}, {"filename": "d.py"}, {"filename": "e/f.py"}]
        assert f.top_level_paths(files) == ["api", "web", "(root)"]


class TestBuildRepoRecord:
    def test_full_record(self):
        rec = f.build_repo_record(
            repo_fixture(),
            commits=[commit_fixture(), commit_fixture("docs: readme", "2026-09-23T00:00:00Z")],
            latest_files=[{"filename": "api/intake.py"}],
            readme_text="# Demo\n\nDemo readme text for the project here ok.",
            now=NOW,
        )
        assert rec["name"] == "demo"
        assert rec["core_purpose"] == "A demo repo"
        assert rec["days_since_push"] == 1
        assert rec["activity_status"] == "ACTIVE"
        assert rec["latest_commit"] == "feat: add intake validation"
        assert rec["recent_functionality"] == "feat: add intake validation (areas: api)"
        assert "docs: readme" in rec["recent_commit_summary"]
        assert rec["has_readme"] is True

    def test_no_commits(self):
        rec = f.build_repo_record(repo_fixture(pushed_at=None), None, None, None, NOW)
        assert rec["latest_commit"] == ""
        assert rec["recent_functionality"] == ""
        assert rec["activity_status"] == "UNKNOWN"
        assert rec["core_purpose"] == "Topics: ai"


class TestMergeHistory:
    def test_today_replaced_others_maxed_and_pruned(self):
        history = {
            "2026-09-24": {"commits": 2},   # today -> replaced
            "2026-09-23": {"commits": 5},   # max(5, 3) kept
            "2026-06-01": {"commits": 9},   # older than 90d -> pruned
        }
        out = f.merge_history(history, {"2026-09-24": 4, "2026-09-23": 3},
                              today="2026-09-24", retention_days=90)
        assert out["2026-09-24"] == {"commits": 4}
        assert out["2026-09-23"] == {"commits": 5}
        assert "2026-06-01" not in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:/solopreneur-github-dashboard && python -m pytest tests/ -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fetch_github_data'`

- [ ] **Step 3: Implement the pure functions in `scripts/fetch_github_data.py`**

```python
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
            history[date] = {"commits": count}          # idempotent replace for today
        else:
            prev = history.get(date, {}).get("commits", 0)
            history[date] = {"commits": max(prev, count)}  # never inflate past days
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).date().isoformat()
    return {d: v for d, v in sorted(history.items()) if d >= cutoff}
```

(plus `fetch_json`, `fetch_all_repos`, `fetch_latest_commits`, `fetch_commit_files`, `fetch_readme_text`, `main()` — implemented in Task 3.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: 18 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/fetch_github_data.py tests/
git commit -m "feat: data pipeline pure functions with tests"
```

---

### Task 3: Data Pipeline — Network Fetch + Live Seed Data

**Files:**
- Modify: `scripts/fetch_github_data.py` (add fetch functions + `main()`)

**Interfaces:**
- Consumes: Task 2 functions.
- Produces on disk (relative to repo root):
  - `data/repos.json` — `{"generated_at": str, "user": str, "repos": [repo_record, ...]}` sorted by `pushed_at` DESC, archived excluded.
  - `data/activity.json` — `{"generated_at": str, "feed": [{"repo","date","message","url"}, ...]}` max 100 entries, newest first.
  - `data/history.json` — `{"YYYY-MM-DD": {"commits": int}, ...}` last 90 days.
  - `data/metadata.json` — `{"generated_at","user","repo_count","archived_excluded","detail_repos","status","errors": [...]}` where status is `"ok"` or `"partial"`.

- [ ] **Step 1: Add fetch functions**

```python
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
```

- [ ] **Step 2: Add `main()`**

```python
def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    errors = []

    repos = fetch_all_repos(USER, TOKEN)
    active = sorted((r for r in repos if not r.get("archived")),
                    key=lambda r: r.get("pushed_at") or "", reverse=True)
    cutoff = now - timedelta(days=DETAIL_WINDOW_DAYS)
    detail = set()
    for r in active[:MAX_DETAIL_REPOS]:
        p = r.get("pushed_at")
        if p and datetime.fromisoformat(p.replace("Z", "+00:00")) >= cutoff:
            detail.add(r["full_name"])

    records, feed, daily_counts = [], [], {}
    for r in active:
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
        "archived_excluded": len(repos) - len(active), "detail_repos": len(detail),
        "status": "ok" if not errors else "partial", "errors": errors[:20],
    })
    print(f"OK: {len(records)} repos ({len(detail)} with detail), {len(feed)} feed entries, "
          f"{len(errors)} errors")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run live against GitHub with token**

Run: `cd D:/solopreneur-github-dashboard && GITHUB_TOKEN=$(gh auth token) python scripts/fetch_github_data.py`
Expected: prints `OK: N repos (...)`, and `data/*.json` exist with real data. Inspect `data/metadata.json` — `status` should be `ok`.

- [ ] **Step 4: Re-run tests, commit**

```bash
python -m pytest tests/ -v   # still green
git add scripts/fetch_github_data.py data/
git commit -m "feat: live data fetch + seed datasets"
```

---

### Task 4: Frontend MVP

**Files:**
- Create: `index.html`
- Create: `assets/css/dashboard.css`
- Create: `assets/js/dashboard.js`

**Interfaces:**
- Consumes: `data/repos.json` (`payload.repos[]` records per Task 2 shape), `data/activity.json` (`payload.feed[]`), `data/metadata.json`.
- Produces: browser dashboard. `localStorage` key `sgcc-v1` holding `{count, days, search, includeArchived, includeForks, sortKey, sortDir, visible: [field keys]}`.

**Behavior spec:** filter bar (count dropdown 10/15/20/25/50/All default 10; pushed-within dropdown 1/2/5/10/15/20/30 days/All; instant search across name/description/core_purpose/topics/languages/recent_functionality/recent_commit_summary/latest_commit; include-archived/include-forks checkboxes). Table columns default: Repository, Core Purpose, Last Push, Days Ago, Recent Functionality, Latest Commit, Activity, Open Issues — all other record fields available via a Customize Fields panel; all preferences persisted. Sortable by clicking Name, Last Push, Days Ago, Open Issues. Activity badge colored per status. Relative timestamps ("3h ago", "2d ago"). CSV export button downloads only currently filtered rows with currently visible columns, filename `github-solopreneur-dashboard-YYYY-MM-DD.csv`. Activity feed section below table (top 15 entries, grouped labels TODAY/YESTERDAY/OLDER). Data-freshness line in header from `metadata.json` (spec §38); graceful fallback banner "Latest data update failed — showing data from `<timestamp>`" if `generated_at` is older than 12h (spec §48). Table horizontally scrolls on small screens (spec §32).

- [ ] **Step 1: Write `index.html`** — semantic header (title "SOLOPRENEUR GITHUB COMMAND CENTER", tagline "Build → Ship → Learn → Improve", freshness line), `<section id="filters">` with the controls, `<details id="fields-panel">` for Customize Fields, `<button id="csv-btn">`, `<div id="status-banner">` (hidden by default), `<section id="kpis-lite">` (repos tracked / matching / archived excluded from metadata), `<table id="repo-table">`, `<section id="activity-feed">`, footer linking to the GitHub repo. Load `assets/js/dashboard.js` with `defer`. All controls with `<label>`s (spec §47 accessibility).

- [ ] **Step 2: Write `assets/css/dashboard.css`** — dark professional theme (CSS custom properties), system font stack, sticky filter bar, responsive table (`overflow-x: auto` wrapper, `white-space: nowrap` on compact columns), status badge colors (ACTIVE #2ea043, RECENT #3fb950-ish teal, COOLING #d29922, STALE #f0883e, DORMANT #8b949e, UNKNOWN #6e7681), high-contrast text, keyboard-focus outlines. No animations beyond subtle hover. ~150 lines.

- [ ] **Step 3: Write `assets/js/dashboard.js`** — full implementation per behavior spec. Core structure:

```js
"use strict";
const CONFIG = {
  activityRules: [[2,"ACTIVE"],[7,"RECENT"],[15,"COOLING"],[30,"STALE"]],
  fallbackStatus: "DORMANT",
  storageKey: "sgcc-v1",
  defaultVisible: ["name","core_purpose","last_push","days_since_push","recent_functionality","latest_commit","activity_status","open_issues"],
  staleHours: 12,
};
const FIELDS = [ /* 23 entries: {key,label} matching every repos.json record key */ ];
// state load/save, fetchAll, applyFilters+sort, renderTable, renderFeed,
// renderFieldsPanel, exportCSV (RFC-4180 quoting), relativeTime(iso), debounced search
```

Key logic: `applyFilters()` filters `state.repos` by days/search/toggles then slices to count; `sortRows()` compares numerically for `days_since_push/open_issues/stars/forks/size`, else lexically (ISO dates sort correctly as strings); `exportCSV()` builds `FIELDS.filter(visible)` headers + filtered rows, Blob download.

- [ ] **Step 4: Smoke test locally**

Run: `cd D:/solopreneur-github-dashboard && python -m http.server 8899` (background), then `curl -s http://localhost:8899/ | head -5` and `curl -s http://localhost:8899/data/repos.json | python -c "import json,sys; print(len(json.load(sys.stdin)['repos']))"`.
Expected: HTML served; repo count printed. JS correctness verified in Task 6 via the live Pages URL.

- [ ] **Step 5: Commit**

```bash
git add index.html assets/
git commit -m "feat: dashboard frontend MVP (filters, fields, sort, CSV, feed)"
```

---

### Task 5: README + Automation Workflow

**Files:**
- Create: `README.md`
- Create: `.github/workflows/update-dashboard.yml`
- Create: `requirements.txt` (`pytest` only)

- [ ] **Step 1: Write README** — sections: What it does; Architecture (ASCII diagram like spec §3); Live URL placeholder; Setup (fork/template, enable Pages: Settings → Pages → Deploy from branch → main → /(root)); Authentication (GITHUB_TOKEN automatic in Actions; local run: `GITHUB_TOKEN=$(gh auth token) python scripts/fetch_github_data.py`); Refresh mechanism (6-hour schedule + manual **Update Dashboard** via Actions tab); Filters & fields; CSV export; Historical data (90-day retention, today-replaced/others-max merge rule, commit counts from fetched detail window — known limitation: partial counts, documented); Security (public repos only, no secrets, GITHUB_TOKEN scoped); Rate limits (Actions token 1,000 req/hr/repo, run uses ~3 calls × detail repos); Local dev (`python -m http.server`); Troubleshooting (workflow failed → last committed data still served); Future enhancements (KPI cards, charts, LLM summaries via Hermes). ~80 lines.

- [ ] **Step 2: Write the workflow**

```yaml
name: Update Dashboard Data
on:
  schedule:
    - cron: "23 */6 * * *"
  workflow_dispatch:
  push:
    branches: [main]
    paths-ignore: ["data/**", "docs/**"]

permissions:
  contents: write

concurrency:
  group: update-dashboard
  cancel-in-progress: true

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Fetch GitHub data
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_USER: itsaslamopenclawdata
        run: python scripts/fetch_github_data.py
      - name: Commit updated data
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/
          if git diff --cached --quiet; then
            echo "No data changes."
          else
            git commit -m "data: update dashboard datasets [skip ci]"
            git push
          fi
```

- [ ] **Step 3: Commit**

```bash
git add README.md .github/workflows/update-dashboard.yml requirements.txt docs/
git commit -m "docs+ci: README, update workflow, implementation plan"
```

---

### Task 6: Push, Deploy, Verify (CI Gate)

**Files:**
- Modify: `README.md` (insert live Pages URL)

- [ ] **Step 1: Create GitHub repo and push**

```bash
cd D:/solopreneur-github-dashboard
gh repo create solopreneur-github-dashboard --public --source . --push
```
Expected: repo created at `https://github.com/itsaslamopenclawdata/solopreneur-github-dashboard`.

- [ ] **Step 2: Enable GitHub Pages**

```bash
gh api repos/itsaslamopenclawdata/solopreneur-github-dashboard/pages -X POST -F "source[branch]=main" -F "source[path]=/"
```
Expected: 201/204 with `html_url`.

- [ ] **Step 3: Trigger workflow and watch the CI gate**

```bash
gh workflow run update-dashboard.yml --repo itsaslamopenclawdata/solopreneur-github-dashboard
sleep 30 && gh run list --repo itsaslamopenclawdata/solopreneur-github-dashboard --workflow=update-dashboard.yml --limit 1
gh run watch <run-id> --repo itsaslamopenclawdata/solopreneur-github-dashboard --exit-status
```
Expected: run succeeds (green). If failed: read logs (`gh run view <id> --log-failed`), fix, re-push, re-watch. Never claim green without watching the run.

- [ ] **Step 4: Verify the live Pages URL**

```bash
curl -s https://itsaslamopenclawdata.github.io/solopreneur-github-dashboard/data/metadata.json
curl -s -o /dev/null -w "%{http_code}" https://itsaslamopenclawdata.github.io/solopreneur-github-dashboard/
```
Expected: metadata JSON with fresh `generated_at` and `status: ok`; HTTP 200 for index. (Pages first deploy can take 1–3 min after push; poll until 200.)

- [ ] **Step 5: Insert live URL into README, final commit + push**

- [ ] **Step 6: Final delivery report** — exact format per spec §60 (STATUS / repo URL / dashboard URL / workflow / schedule / repos available / implemented ✓ / not implemented − / security / manual actions / known limitations / recommended next upgrade).

---

## Self-Review Notes (completed during planning)

- **Spec coverage:** V1 scope items (§3, §5, §7–11, §12, §13, §14, §19–21, §24, §28, §31–32, §34–39, §40–42, §43 default, §44–51 adapted) all map to Tasks 1–6. Deferred items listed in plan header.
- **Placeholders:** none; all code shown in full for Tasks 1–3 and 5; Task 4 behavior fully specified with module skeleton (full code written during execution, verified in Task 6 Step 4).
- **Type consistency:** `repo_record` keys shared between Python `build_repo_record` and JS `FIELDS` catalog — same 23 keys. `activity.json` feed shape `{repo,date,message,url}` consistent pipeline→frontend.
