"""GitHub API integration: post review results to PR.

Uses the GitHub REST API via httpx — a hard dependency (declared in
pyproject); no fallback path.
"""

import httpx
import structlog

from junior.config import Settings
from junior.github_api import API_BASE, headers as github_headers
from junior.runbooks.code_review.models import ReviewComment, ReviewResult
from junior.publish.core import MAX_INLINE_COMMENTS, format_inline_comment, format_summary

logger = structlog.get_logger()


def post_review(settings: Settings, result: ReviewResult) -> None:
    """Post review results to GitHub PR."""
    owner, repo = settings.output.github_repository.split("/", 1)
    pr_number = settings.output.github_event_number
    token = settings.output.github_token

    # Post summary as PR comment
    summary = format_summary(result, settings=settings)
    _post_comment(owner, repo, pr_number, token, summary)
    logger.info("posted PR comment", repo=settings.output.github_repository, pr=pr_number)

    # Post inline comments as PR review (requires commit SHA)
    if settings.output.ci_commit_sha:
        inline_comments = [c for c in result.comments if c.file_path and c.line_number]
        if inline_comments:
            _post_review_comments(owner, repo, pr_number, token, inline_comments, settings)
    else:
        logger.info("no commit SHA available, skipping inline comments")


def _post_comment(owner: str, repo: str, pr_number: int, token: str, body: str) -> None:
    """Post a general comment on a PR."""
    resp = httpx.post(
        f"{API_BASE}/repos/{owner}/{repo}/issues/{pr_number}/comments",
        headers=github_headers(token),
        json={"body": body},
        timeout=30,
    )
    resp.raise_for_status()


def _post_review_comments(
    owner: str,
    repo: str,
    pr_number: int,
    token: str,
    comments: list[ReviewComment],
    settings: Settings,
) -> None:
    """Post inline comments as a PR review."""
    review_comments = [
        {
            "path": c.file_path,
            "line": c.line_number,
            "body": format_inline_comment(c),
        }
        for c in comments[:MAX_INLINE_COMMENTS]
    ]

    resp = httpx.post(
        f"{API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
        headers=github_headers(token),
        json={
            "body": "Junior AI review — inline comments below.",
            "event": "COMMENT",
            "comments": review_comments,
            "commit_id": settings.output.ci_commit_sha,
        },
        timeout=30,
    )
    if resp.status_code == 422:
        # Line mapping failed — post as regular comments instead
        logger.warning("inline review failed, posting as regular comments")
        for rc in review_comments:
            _post_comment(
                owner, repo, pr_number, token, f"`{rc['path']}:{rc['line']}`\n\n{rc['body']}"
            )
    else:
        resp.raise_for_status()
        logger.info("posted inline review", comments=len(review_comments))
