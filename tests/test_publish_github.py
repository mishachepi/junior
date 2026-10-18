"""GitHub publish: summary comment + inline review."""

from types import SimpleNamespace

import pytest

from junior.config import OutputSettings, Settings
from junior.publish import github
from junior.runbooks.code_review.models import ReviewComment, ReviewOutput, ReviewResult


def _result() -> ReviewResult:
    return ReviewResult(output=ReviewOutput(
        summary="s",
        comments=[
            ReviewComment(category="logic", severity="high", message="m",
                          file_path="a.py", line_number=3),
            ReviewComment(category="naming", severity="low", message="general"),
        ],
    ))


@pytest.fixture
def posts(monkeypatch):
    httpx = pytest.importorskip("httpx")
    calls: list[tuple[str, dict]] = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs["json"]))
        return SimpleNamespace(status_code=201, raise_for_status=lambda: None)

    monkeypatch.setattr(httpx, "post", fake_post)
    return calls


@pytest.mark.parametrize("sha", [None, "abc123"])
def test_inline_review_posted_with_or_without_commit_sha(posts, sha):
    """GitHub Actions sets no CI_COMMIT_SHA — inline comments must still go out;
    `commit_id` is sent only when a SHA is known."""
    settings = Settings(output=OutputSettings(
        github_token="t", github_repository="o/r", github_event_number=7, ci_commit_sha=sha,
    ))

    github.post_review(settings, _result())

    review = [body for url, body in posts if url.endswith("/pulls/7/reviews")]
    assert len(review) == 1
    assert [c["path"] for c in review[0]["comments"]] == ["a.py"]
    assert review[0].get("commit_id") == sha
