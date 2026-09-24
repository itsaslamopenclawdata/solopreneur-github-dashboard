# Solopreneur GitHub Command Center

A static, serverless daily dashboard that answers — in under a minute:

**What are my projects? What did I work on recently? What changed? What's active? What's gone stale?**

Live dashboard: `https://itsaslamopenclawdata.github.io/solopreneur-github-dashboard/`

## What it does

- Lists your GitHub repositories ordered by most recent push (`pushed_at DESC`)
- Dropdowns: show 10 / 15 / 20 / 25 / 50 / All repos, filtered by last-push window (1–30 days)
- Instant client-side search across name, description, core purpose, topics, languages, and recent commit messages
- **Core Purpose** per repo, derived from: description → README → topics → *"Purpose not yet documented"*
- **Recent Functionality** per repo: latest commit message + top-level areas changed (e.g. `feat: add intake validation (areas: api)`)
- **Activity status** badge per repo: ACTIVE (0–2d) · RECENT (3–7d) · COOLING (8–15d) · STALE (16–30d) · DORMANT (>30d)
- **Customize Fields**: toggle any of 26 columns on/off; preferences survive refresh (localStorage)
- Sortable columns, filtered **CSV export**, recent-activity feed (Today / Yesterday / older)
- Data refreshed automatically every 6 hours by GitHub Actions

## Architecture

```text
GitHub REST API
      │
      ▼
GitHub Actions (scheduled + manual)   ── GITHUB_TOKEN, server-side only
      │  scripts/fetch_github_data.py (Python stdlib)
      ▼
data/*.json  (repos / activity / history / metadata)  ← committed to main
      │
      ▼
GitHub Pages  ── static HTML/CSS/JS, reads JSON client-side
      │
      ▼
Browser (no API keys, no rate limits, works if Actions is down)
```

## Repository structure

```text
├── index.html                  # dashboard page
├── assets/css/dashboard.css    # styles
├── assets/js/dashboard.js      # all client logic (no dependencies)
├── data/                       # generated datasets (do not hand-edit)
│   ├── repos.json              # per-repo records incl. core_purpose, recent_functionality
│   ├── activity.json           # recent commit feed (max 100)
│   ├── history.json            # per-day commit counts, 90-day retention
│   └── metadata.json           # generated_at, counts, status, errors
├── scripts/fetch_github_data.py  # data pipeline (stdlib only)
├── tests/                      # pytest suite for pipeline logic
└── .github/workflows/update-dashboard.yml
```

## Setup

1. Fork or clone this repository.
2. In the workflow file, replace `GITHUB_USER: itsaslamopenclawdata` with your username.
3. Run the workflow once manually (**Actions → Update Dashboard Data → Run workflow**) to generate data.
4. Enable Pages: **Settings → Pages → Build and deployment → Deploy from a branch → `main` / `/(root)`**.
5. Bookmark the Pages URL.

No other configuration is required for public repositories.

## Authentication

- **In GitHub Actions:** the built-in `GITHUB_TOKEN` is used automatically — no secrets to create. It reads only public repositories here; nothing is exposed to the browser.
- **Locally:** `GITHUB_TOKEN=$(gh auth token) python scripts/fetch_github_data.py` (optional — works unauthenticated within the 60 req/hr public limit).

Never paste a token into HTML/JS or commit one — the browser never calls the GitHub API.

## Data refresh

- **Schedule:** every 6 hours (`23 */6 * * *` UTC) plus a `push` trigger on `main`.
- **Manual:** Actions → *Update Dashboard Data* → *Run workflow*.
- If a run fails, the last successfully committed data keeps serving; the dashboard shows a "data is stale / update failed" banner with the timestamp (§48-style graceful degradation).
- If a run produces no changes, nothing is committed.

## Historical data

`data/history.json` stores per-day commit counts with a 90-day retention window. Merge rule: today's count is **replaced** each run (idempotent); past days keep the **max** seen (never inflated by re-runs). *Known limitation:* counts come from the detail window (repos pushed within the last 90 days, up to 5 commits fetched per repo), so they are indicative rather than exhaustive.

## Rate limits

A run makes roughly `1 + 3 × (repos with detail)` API calls (~22 for this account) — trivially inside the `GITHUB_TOKEN` limit of 1,000 req/hr per repository.

## Local development

```bash
python -m http.server 8899
# open http://localhost:8899/
python -m pytest tests/ -v   # pipeline unit tests
```

## Security notes

- Dashboard exposes **public repository data only** (hard rule: §35 of the design spec). Do not point it at private repos on a public Pages site.
- Activity status thresholds and UI preferences live in client-side config — tweak `CONFIG` in `assets/js/dashboard.js` and the `STATUS_RULES` in the Python script.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Dashboard shows "data unavailable" | Run the workflow manually; check the Actions log |
| Banner says data is stale | Check the latest workflow run's exit status and log |
| A repo shows no recent functionality | It was pushed outside the 90-day detail window — raise `DETAIL_WINDOW_DAYS` |
| Repo missing entirely | It may be archived; tick "Include archived" |

## Future enhancements (deferred by design)

KPI cards, activity charts (Chart.js), language/activity filters, dark/light mode, repository health signals, LLM-written functionality summaries refreshed by an external job. See `docs/superpowers/plans/2026-09-24-solopreneur-github-command-center.md` for the staged plan.

## License

MIT — see [LICENSE](LICENSE).
