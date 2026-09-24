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
        assert f.days_between("2026-09-23T05:00:00Z", NOW) == 0
        assert f.days_between("2026-09-23T04:00:00Z", NOW) == 1
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
        assert f.core_purpose(None, rd, ["honey"]) == \
            "This project automates beekeeping operations end to end."

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
            commits=[commit_fixture(),
                     commit_fixture("docs: readme", "2026-09-23T00:00:00Z")],
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
        rec = f.build_repo_record(
            repo_fixture(pushed_at=None, description=None), None, None, None, NOW)
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
