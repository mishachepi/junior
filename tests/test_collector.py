"""Tests for collector: diff parsing, file status."""

from pathlib import Path
from types import SimpleNamespace

from junior.collect.core.diff import (
    _detect_file_status,
    _parse_diff_header,
    _split_diff_by_file,
    resolve_base_sha,
)
from junior.config import ContextSettings, OutputSettings, Settings
from junior.collect.github import _parse_github_comments
from junior.collect.gitlab import _fetch_gitlab_comments
from junior.models import FileStatus


# --- finalize_comments ---


def test_finalize_comments_drops_empty_sorts_and_caps(monkeypatch):
    from junior.collect.core import comments as comments_mod
    from junior.collect.core.comments import finalize_comments
    from junior.runbooks.code_review.models import MRComment

    monkeypatch.setattr(comments_mod, "MAX_COMMENTS", 3)
    raw = [
        MRComment(body="c5", created_at="2025-01-05"),
        MRComment(body="   ", created_at="2025-01-09"),  # empty after strip → dropped
        MRComment(body="c1", created_at="2025-01-01"),
        MRComment(body="c4", created_at="2025-01-04"),
        MRComment(body="c3", created_at="2025-01-03"),
        MRComment(body="c2", created_at="2025-01-02"),
    ]
    out = finalize_comments(raw)
    # sorted oldest→newest, newest 3 kept, blank dropped
    assert [c.body for c in out] == ["c3", "c4", "c5"]


# --- _parse_diff_header ---


def test_parse_diff_header_standard():
    assert _parse_diff_header("diff --git a/src/foo.py b/src/foo.py") == "src/foo.py"


def test_parse_diff_header_noprefix():
    assert _parse_diff_header("diff --git foo.py foo.py") == "foo.py"


def test_parse_diff_header_noprefix_nested():
    assert _parse_diff_header("diff --git src/bar/baz.py src/bar/baz.py") == "src/bar/baz.py"


def test_parse_diff_header_rename_standard():
    assert _parse_diff_header("diff --git a/old.py b/new.py") == "new.py"


# --- _split_diff_by_file ---

SAMPLE_DIFF_STANDARD = """\
diff --git a/hello.py b/hello.py
index abc..def 100644
--- a/hello.py
+++ b/hello.py
@@ -1,3 +1,4 @@
 line1
+added
diff --git a/world.py b/world.py
new file mode 100644
--- /dev/null
+++ b/world.py
@@ -0,0 +1 @@
+new file
"""

SAMPLE_DIFF_NOPREFIX = """\
diff --git hello.py hello.py
index abc..def 100644
--- hello.py
+++ hello.py
@@ -1,3 +1,4 @@
 line1
+added
diff --git world.py world.py
new file mode 100644
--- /dev/null
+++ world.py
@@ -0,0 +1 @@
+new file
"""


def test_split_diff_standard():
    chunks = _split_diff_by_file(SAMPLE_DIFF_STANDARD)
    assert set(chunks.keys()) == {"hello.py", "world.py"}
    assert "+added" in chunks["hello.py"]
    assert "+new file" in chunks["world.py"]


def test_split_diff_noprefix():
    chunks = _split_diff_by_file(SAMPLE_DIFF_NOPREFIX)
    assert set(chunks.keys()) == {"hello.py", "world.py"}
    assert "+added" in chunks["hello.py"]


def test_split_diff_empty():
    assert _split_diff_by_file("") == {}
    assert _split_diff_by_file("   \n  ") == {}


# --- _detect_file_status ---


def test_detect_status_added():
    diff = "--- /dev/null\n+++ b/new.py\n"
    assert _detect_file_status(diff, Path("/nonexistent")) == FileStatus.ADDED


def test_detect_status_deleted():
    diff = "--- a/old.py\n+++ /dev/null\n"
    assert _detect_file_status(diff, Path("/nonexistent")) == FileStatus.DELETED


def test_detect_status_renamed():
    diff = "rename from old.py\nrename to new.py\n"
    assert _detect_file_status(diff, Path("/nonexistent")) == FileStatus.RENAMED


def test_detect_status_modified(tmp_path):
    (tmp_path / "exists.py").write_text("content")
    diff = "--- a/exists.py\n+++ b/exists.py\n"
    assert _detect_file_status(diff, tmp_path / "exists.py") == FileStatus.MODIFIED


# --- GitLab comment parsing ---


def _gl_discussion(*, resolved=False, notes):
    return SimpleNamespace(attributes={"resolved": resolved, "notes": notes})


def test_gitlab_comments_filters_system_notes_and_empty():
    mr = SimpleNamespace(
        discussions=SimpleNamespace(
            list=lambda get_all: [
                _gl_discussion(notes=[
                    {"system": True, "body": "assigned", "author": {"username": "bot"}, "created_at": "2025-01-01"},
                    {"system": False, "body": "  ", "author": {"username": "alice"}, "created_at": "2025-01-02"},
                    {"system": False, "body": "real comment", "author": {"username": "alice"}, "created_at": "2025-01-03"},
                ]),
            ]
        )
    )
    out = _fetch_gitlab_comments(mr)
    assert len(out) == 1
    assert out[0].author == "alice"
    assert out[0].body == "real comment"


def test_gitlab_comments_inline_position():
    mr = SimpleNamespace(
        discussions=SimpleNamespace(
            list=lambda get_all: [
                _gl_discussion(resolved=True, notes=[
                    {
                        "body": "looks off",
                        "author": {"username": "bob"},
                        "created_at": "2025-01-04",
                        "position": {"new_path": "src/foo.py", "new_line": 42},
                    }
                ])
            ]
        )
    )
    out = _fetch_gitlab_comments(mr)
    assert out[0].file_path == "src/foo.py"
    assert out[0].line_number == 42
    assert out[0].resolved is True


def test_gitlab_comments_caps_at_max(monkeypatch):
    from junior.collect import gitlab as gl_mod
    from junior.collect.core import comments as comments_mod

    monkeypatch.setattr(comments_mod, "MAX_COMMENTS", 3)
    notes = [
        {"body": f"c{i}", "author": {"username": "u"}, "created_at": f"2025-01-{i:02d}"}
        for i in range(1, 11)
    ]
    mr = SimpleNamespace(
        discussions=SimpleNamespace(list=lambda get_all: [_gl_discussion(notes=notes)])
    )
    out = gl_mod._fetch_gitlab_comments(mr)
    assert len(out) == 3
    assert [c.body for c in out] == ["c8", "c9", "c10"]


# --- non-HTTPS cleartext-token warning ---


def _gitlab_settings(url: str, token: str) -> Settings:
    return Settings(
        output=OutputSettings(
            ci_server_url=url,
            gitlab_token=token,
            ci_project_id=1,
            ci_merge_request_iid=1,
        )
    )


def _warned_cleartext(records) -> bool:
    return any(
        r.get("event", "").startswith("CI_SERVER_URL is not HTTPS") for r in records
    )


def test_collect_warns_on_non_https_with_token():
    from structlog.testing import capture_logs

    from junior.collect.gitlab import _fetch_gitlab_metadata

    with capture_logs() as logs:
        # The API call then soft-fails (no server) — we only assert the warning fired.
        _fetch_gitlab_metadata(_gitlab_settings("http://gitlab.intranet", "secret"))
    assert _warned_cleartext(logs)


def test_collect_no_warning_on_https():
    from structlog.testing import capture_logs

    from junior.collect.gitlab import _fetch_gitlab_metadata

    with capture_logs() as logs:
        _fetch_gitlab_metadata(_gitlab_settings("https://gitlab.com", "secret"))
    assert not _warned_cleartext(logs)


def test_collect_no_warning_on_uppercase_https_scheme():
    from structlog.testing import capture_logs

    from junior.collect.gitlab import _fetch_gitlab_metadata

    # URI schemes are case-insensitive (RFC 3986) — HTTPS is still encrypted.
    with capture_logs() as logs:
        _fetch_gitlab_metadata(_gitlab_settings("HTTPS://gitlab.com", "secret"))
    assert not _warned_cleartext(logs)


def test_collect_no_warning_when_token_empty():
    from structlog.testing import capture_logs

    from junior.collect.gitlab import _fetch_gitlab_metadata

    with capture_logs() as logs:
        _fetch_gitlab_metadata(_gitlab_settings("http://gitlab.intranet", ""))
    assert not _warned_cleartext(logs)


def test_publish_warns_on_non_https_with_token():
    from structlog.testing import capture_logs

    from junior.publish.gitlab import post_review
    from junior.runbooks.code_review.models import ReviewOutput, ReviewResult

    with capture_logs() as logs:
        try:
            post_review(
                _gitlab_settings("http://gitlab.intranet", "secret"),
                ReviewResult(output=ReviewOutput(summary="s")),
            )
        except Exception:
            pass  # no server — warning fires before the API call fails
    assert _warned_cleartext(logs)


def test_publish_no_warning_on_https():
    from structlog.testing import capture_logs

    from junior.publish.gitlab import post_review
    from junior.runbooks.code_review.models import ReviewOutput, ReviewResult

    with capture_logs() as logs:
        try:
            post_review(
                _gitlab_settings("https://gitlab.com", "secret"),
                ReviewResult(output=ReviewOutput(summary="s")),
            )
        except Exception:
            pass
    assert not _warned_cleartext(logs)


# --- GitHub comment parsing ---


def test_github_parses_issue_and_inline_comments():
    issue = [
        {"body": "general note", "user": {"login": "alice"}, "created_at": "2025-01-02"},
        {"body": "", "user": {"login": "spam"}, "created_at": "2025-01-03"},
    ]
    inline = [
        {
            "body": "fix this line",
            "user": {"login": "bob"},
            "created_at": "2025-01-01",
            "path": "src/foo.py",
            "line": 10,
        }
    ]
    out = _parse_github_comments(issue, inline)
    assert [c.body for c in out] == ["fix this line", "general note"]
    assert out[0].file_path == "src/foo.py"
    assert out[0].line_number == 10
    assert out[1].file_path is None


# --- resolve_base_sha ---


def test_resolve_base_sha_cli_wins_over_ci():
    s = Settings(
        context=ContextSettings(base_sha="cafebabe"),
        output=OutputSettings(
            ci_merge_request_diff_base_sha="deadbeef",
            ci_commit_before_sha="abc123",
        ),
    )
    assert resolve_base_sha(s) == ("cafebabe", "cli")


def test_resolve_base_sha_skips_zero_placeholder():
    # Zero SHA is what GitLab/GitHub emit on first push to a branch.
    s = Settings(
        output=OutputSettings(
            ci_commit_before_sha="0" * 40,
            github_event_before="abcdef0",
        )
    )
    assert resolve_base_sha(s) == ("abcdef0", "github_event_before")


def test_resolve_base_sha_returns_none_when_all_empty():
    s = Settings()
    assert resolve_base_sha(s) == (None, "none")


def test_resolve_base_sha_priority_order():
    # MR base wins over push before-SHA when both present (MR runbook).
    s = Settings(
        output=OutputSettings(
            ci_merge_request_diff_base_sha="mrbase",
            ci_commit_before_sha="pushbefore",
        )
    )
    assert resolve_base_sha(s) == ("mrbase", "mr_diff_base")
