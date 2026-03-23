"""GitHub API integration: post review results to PR.

Uses the GitHub REST API via httpx (no extra dependencies —
httpx is already pulled in by pydantic-ai/anthropic/openai SDKs).
Falls back to subprocess `gh` CLI if httpx is not available.
"""

import subprocess

import structlog

from junior.config import Settings
from junior.models import ReviewComment, ReviewResult
from junior.publish.core import MAX_INLINE_COMMENTS, format_inline_comment, format_summary

logger = structlog.get_logger()

_API_BASE = "https://api.github.com"


def post_review(settings: Settings, result: ReviewResult) -> None:
    """Post review results to GitHub PR."""
    owner, repo = settings.github_repository.split("/", 1)
    pr_number = settings.github_event_number
    token = settings.github_token

    # Post summary as PR comment
    summary = format_summary(result, settings=settings)
    _post_comment(owner, repo, pr_number, token, summary)
    logger.info("posted PR comment", repo=settings.github_repository, pr=pr_number)

    # Post inline comments as PR review (requires commit SHA)
    if settings.ci_commit_sha:
        inline_comments = [c for c in result.comments if c.file_path and c.line_number]
        if inline_comments:
            _post_review_comments(owner, repo, pr_number, token, inline_comments, settings)
    else:
        logger.info("no commit SHA available, skipping inline comments")


def _post_comment(owner: str, repo: str, pr_number: int, token: str, body: str) -> None:
    """Post a general comment on a PR."""
    try:
        import httpx

        resp = httpx.post(
            f"{_API_BASE}/repos/{owner}/{repo}/issues/{pr_number}/comments",
            headers=_headers(token),
            json={"body": body},
            timeout=30,
        )
        resp.raise_for_status()
    except ImportError:
        _gh_cli_comment(owner, repo, pr_number, body)


def _post_review_comments(
    owner: str,
    repo: str,
    pr_number: int,
    token: str,
    comments: list[ReviewComment],
    settings: Settings,
) -> None:
    """Post inline comments as a PR review."""
    review_comments = []
    for c in comments[:MAX_INLINE_COMMENTS]:
        review_comments.append(
            {
                "path": c.file_path,
                "line": c.line_number,
                "body": format_inline_comment(c),
            }
        )

    try:
        import httpx

        resp = httpx.post(
            f"{_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            headers=_headers(token),
            json={
                "body": "Junior AI review — inline comments below.",
                "event": "COMMENT",
                "comments": review_comments,
                "commit_id": settings.ci_commit_sha,
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
    except ImportError:
        logger.warning("httpx not available, skipping inline comments")


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _gh_cli_comment(owner: str, repo: str, pr_number: int, body: str) -> None:
    """Fallback: post comment via `gh` CLI."""
    try:
        subprocess.run(
            ["gh", "pr", "comment", str(pr_number), "--repo", f"{owner}/{repo}", "--body", body],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        raise RuntimeError(f"Failed to post GitHub comment (gh CLI): {e}")
