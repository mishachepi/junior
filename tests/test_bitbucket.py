"""Bitbucket DC vertical: collect (API metadata), publish (comments), runbook."""

import httpx
import pytest

from junior.collect.bitbucket import (
    _parse_bitbucket_comments,
    _paginate_activities,
    collect,
)
from junior.config import OutputSettings, Settings
from junior.runbooks.code_review.models import (
    Recommendation,
    ReviewCategory,
    ReviewComment,
    ReviewContext,
    ReviewOutput,
    ReviewResult,
    Severity,
)
from junior.publish.bitbucket import post_review
from junior.runbook import registry

BITBUCKET_ENV_VARS = (
    "BITBUCKET_URL",
    "BITBUCKET_TOKEN",
    "BITBUCKET_PROJECT",
    "BITBUCKET_REPO",
    "BITBUCKET_PR_ID",
)


@pytest.fixture(autouse=True)
def _no_ambient_bitbucket_env(monkeypatch):
    for var in BITBUCKET_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def _settings() -> Settings:
    return Settings(
        output=OutputSettings(
            bitbucket_url="https://bitbucket.example.com",
            bitbucket_token="secret-token",
            bitbucket_project="PROJ",
            bitbucket_repo="my-repo",
            bitbucket_pr_id=42,
        )
    )


_PR_URL = (
    "https://bitbucket.example.com/rest/api/1.0/projects/PROJ/repos/my-repo/pull-requests/42"
)


# --- HTTP fakes -------------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self._payload = payload if payload is not None else {}
        self.status_code = status_code

    @property
    def is_success(self):
        return self.status_code < 400

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeClient:
    """Stands in for httpx.Client: returns queued responses, records requests."""

    def __init__(self, responses, **kwargs):
        self._responses = list(responses)
        self.init_kwargs = kwargs
        self.requests: list[tuple[str, dict | None]] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, params=None):
        self.requests.append((url, params))
        return self._responses.pop(0)


# --- collect: pagination ----------------------------------------------------


def test_paginate_activities_follows_next_page_start():
    client = _FakeClient(
        [
            _FakeResponse({"values": [{"id": 1}], "isLastPage": False, "nextPageStart": 7}),
            _FakeResponse({"values": [{"id": 2}], "isLastPage": True}),
        ]
    )
    out = _paginate_activities(client, f"{_PR_URL}/activities")
    assert [a["id"] for a in out] == [1, 2]
    assert client.requests[0][1] == {"start": 0, "limit": 100}
    assert client.requests[1][1] == {"start": 7, "limit": 100}


def test_paginate_activities_stops_without_next_page_start():
    client = _FakeClient(
        [_FakeResponse({"values": [{"id": 1}], "isLastPage": False})]  # malformed page
    )
    out = _paginate_activities(client, f"{_PR_URL}/activities")
    assert len(out) == 1


# --- collect: comment parsing -----------------------------------------------


def test_parse_comments_filters_non_commented_and_flattens_threads():
    activities = [
        {"action": "APPROVED", "user": {"name": "carol"}},
        {
            "action": "COMMENTED",
            "comment": {
                "text": "thread root",
                "author": {"name": "alice"},
                "createdDate": 1735689600000,
                "comments": [
                    {
                        "text": "nested reply",
                        "author": {"name": "bob"},
                        "createdDate": 1735693200000,
                        "comments": [],
                    }
                ],
            },
        },
    ]
    out = _parse_bitbucket_comments(activities)
    assert [c.body for c in out] == ["thread root", "nested reply"]
    assert [c.author for c in out] == ["alice", "bob"]


def test_parse_comments_inline_anchor_applies_to_thread():
    activities = [
        {
            "action": "COMMENTED",
            "commentAnchor": {"path": "src/foo.py", "line": 12, "lineType": "ADDED"},
            "comment": {
                "text": "looks off",
                "author": {"name": "bob"},
                "createdDate": 1735689600000,
                "comments": [
                    {"text": "agreed", "author": {"name": "alice"}, "createdDate": 1735693200000}
                ],
            },
        }
    ]
    out = _parse_bitbucket_comments(activities)
    assert out[0].file_path == "src/foo.py"
    assert out[0].line_number == 12
    assert out[1].file_path == "src/foo.py"  # replies inherit the thread anchor


def test_parse_comments_skips_empty_and_caps_at_max(monkeypatch):
    from junior.collect import bitbucket as bb_mod
    from junior.collect.core import comments as comments_mod

    monkeypatch.setattr(comments_mod, "MAX_COMMENTS", 3)
    activities = [
        {
            "action": "COMMENTED",
            "comment": {
                "text": f"c{i}" if i else "  ",
                "author": {"name": "u"},
                "createdDate": 1735689600000 + i * 1000,
            },
        }
        for i in range(10)
    ]
    out = bb_mod._parse_bitbucket_comments(activities)
    assert [c.body for c in out] == ["c7", "c8", "c9"]


# --- collect: API wiring ----------------------------------------------------


def test_collect_sends_bearer_token_and_injects_base_sha(monkeypatch):
    from junior.collect import bitbucket as bb_mod

    made_clients: list[_FakeClient] = []

    def fake_client(**kwargs):
        client = _FakeClient(
            [
                _FakeResponse(
                    {
                        "title": "PR title",
                        "description": "PR description",
                        "toRef": {"latestCommit": "abc123def"},
                    }
                ),
                _FakeResponse({"values": [], "isLastPage": True}),
            ],
            **kwargs,
        )
        made_clients.append(client)
        return client

    monkeypatch.setattr(httpx, "Client", fake_client)

    seen_settings: list[Settings] = []

    def fake_collect_base(settings):
        seen_settings.append(settings)
        return ReviewContext()

    monkeypatch.setattr(bb_mod, "collect_base", fake_collect_base)

    context = collect(_settings())

    client = made_clients[0]
    assert client.init_kwargs["headers"]["Authorization"] == "Bearer secret-token"
    assert client.requests[0][0] == _PR_URL
    assert client.requests[1][0] == f"{_PR_URL}/activities"
    # toRef.latestCommit becomes the diff base (no CI variable on Bitbucket DC)
    assert seen_settings[0].context.base_sha == "abc123def"
    assert context.mr_title == "PR title"
    assert context.mr_description == "PR description"


def test_collect_survives_api_failure(monkeypatch):
    from junior.collect import bitbucket as bb_mod

    def boom(**kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(httpx, "Client", boom)
    monkeypatch.setattr(bb_mod, "collect_base", lambda settings: ReviewContext())

    context = collect(_settings())  # soft failure: plain context, no metadata
    assert context.mr_description == ""
    assert context.comments == []


# --- publish ----------------------------------------------------------------


def _review_result() -> ReviewResult:
    return ReviewResult(
        output=ReviewOutput(
            summary="One issue found.",
            recommendation=Recommendation.COMMENT,
            comments=[
                ReviewComment(
                    category=ReviewCategory.BUG,
                    severity=Severity.HIGH,
                    message="Off-by-one",
                    file_path="src/foo.py",
                    line_number=12,
                ),
                ReviewComment(
                    category=ReviewCategory.LOGIC,
                    severity=Severity.LOW,
                    message="General remark",  # no file/line — summary only
                ),
            ],
        ),
    )


def _record_posts(monkeypatch, statuses):
    """Patch httpx.post to return queued statuses and record each call."""
    posts: list[dict] = []
    queue = list(statuses)

    def fake_post(url, headers=None, json=None, timeout=None):
        posts.append({"url": url, "headers": headers, "json": json})
        return _FakeResponse(status_code=queue.pop(0) if queue else 200)

    monkeypatch.setattr(httpx, "post", fake_post)
    return posts


def test_post_review_posts_summary_and_anchored_inline(monkeypatch):
    posts = _record_posts(monkeypatch, [200, 201])

    post_review(_settings(), _review_result())

    assert len(posts) == 2
    summary, inline = posts
    assert summary["url"] == f"{_PR_URL}/comments"
    assert summary["headers"]["Authorization"] == "Bearer secret-token"
    assert "Junior Code Review" in summary["json"]["text"]
    assert "anchor" not in summary["json"]

    assert inline["json"]["anchor"] == {
        "path": "src/foo.py",
        "line": 12,
        "lineType": "ADDED",
        "fileType": "TO",
        "diffType": "EFFECTIVE",
    }
    assert "Off-by-one" in inline["json"]["text"]


def test_inline_anchor_rejection_falls_back_to_general_comment(monkeypatch):
    # summary OK, inline anchor rejected (line outside diff), fallback OK
    posts = _record_posts(monkeypatch, [200, 400, 200])

    post_review(_settings(), _review_result())

    assert len(posts) == 3
    fallback = posts[2]
    assert "anchor" not in fallback["json"]
    assert fallback["json"]["text"].startswith("`src/foo.py:12`")
    assert "Off-by-one" in fallback["json"]["text"]


def test_failed_summary_post_raises(monkeypatch):
    _record_posts(monkeypatch, [500])
    with pytest.raises(RuntimeError, match="HTTP 500"):
        post_review(_settings(), _review_result())


# --- runbook ----------------------------------------------------------------


def test_runbook_is_registered():
    runbook = registry.get_runbook("bitbucket_pr_review")
    assert runbook.name == "bitbucket_pr_review"
    assert runbook.needs_git is True


def test_runbook_declares_env_vars():
    runbook = registry.get_runbook("bitbucket_pr_review")
    assert tuple(v.name for v in runbook.env_vars) == BITBUCKET_ENV_VARS
    assert all(v.required for v in runbook.env_vars)


def test_validate_requires_all_fields_for_publish():
    runbook = registry.get_runbook("bitbucket_pr_review")
    errors = runbook.validate(Settings(), publish_enabled=True)
    for var in BITBUCKET_ENV_VARS:
        assert any(var in e for e in errors), f"no error mentions {var}"


def test_validate_rejects_plain_http():
    runbook = registry.get_runbook("bitbucket_pr_review")
    settings = Settings(
        output=OutputSettings(
            bitbucket_url="http://bitbucket.example.com",
            bitbucket_token="t",
            bitbucket_project="P",
            bitbucket_repo="r",
            bitbucket_pr_id=1,
        )
    )
    errors = runbook.validate(settings, publish_enabled=True)
    assert errors == ["BITBUCKET_URL must use HTTPS (the access token is sent as a header)."]


def test_validate_passes_with_full_config():
    runbook = registry.get_runbook("bitbucket_pr_review")
    assert runbook.validate(_settings(), publish_enabled=True) == []


def test_validate_skipped_without_publish():
    runbook = registry.get_runbook("bitbucket_pr_review")
    assert runbook.validate(Settings(), publish_enabled=False) == []
