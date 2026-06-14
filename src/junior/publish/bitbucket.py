"""Bitbucket Data Center API integration: post review results to a PR.

Uses the Bitbucket DC 1.0 REST API via httpx (lazy-imported inside functions
so importing this module stays cheap).
"""

import structlog

from junior.bitbucket_api import headers as bitbucket_headers, pr_api_base
from junior.config import Settings
from junior.runbooks.code_review.models import ReviewComment, ReviewResult
from junior.publish.core import MAX_INLINE_COMMENTS, format_inline_comment, format_summary

logger = structlog.get_logger()


def post_review(settings: Settings, result: ReviewResult) -> None:
    """Post review results to a Bitbucket DC pull request."""
    out = settings.output
    comments_url = (
        pr_api_base(out.bitbucket_url, out.bitbucket_project, out.bitbucket_repo, out.bitbucket_pr_id)
        + "/comments"
    )
    token = out.bitbucket_token

    # Post summary as a general PR comment
    summary = format_summary(result, settings=settings)
    _post_comment(comments_url, token, summary)
    logger.info(
        "posted PR comment",
        project=out.bitbucket_project,
        repo=out.bitbucket_repo,
        pr=out.bitbucket_pr_id,
    )

    # Post inline comments anchored to the effective diff
    inline_comments = [c for c in result.comments if c.file_path and c.line_number]
    posted = 0
    for comment in inline_comments[:MAX_INLINE_COMMENTS]:
        if _post_inline_comment(comments_url, token, comment):
            posted += 1
    if posted:
        logger.info("posted inline comments", count=posted)


def _post_comment(comments_url: str, token: str, text: str) -> None:
    """Post a general comment on a PR."""
    import httpx

    resp = httpx.post(
        comments_url,
        headers=bitbucket_headers(token),
        json={"text": text},
        timeout=30,
    )
    resp.raise_for_status()


def _post_inline_comment(comments_url: str, token: str, comment: ReviewComment) -> bool:
    """Post a single comment anchored to a diff line. Returns True on success.

    If Bitbucket rejects the anchor (e.g. the line is outside the effective
    diff), degrade to a general comment carrying the `file:line` location —
    same fallback the GitHub publisher uses.
    """
    import httpx

    body = format_inline_comment(comment)
    try:
        resp = httpx.post(
            comments_url,
            headers=bitbucket_headers(token),
            json={
                "text": body,
                "anchor": {
                    "path": comment.file_path,
                    "line": comment.line_number,
                    "lineType": "ADDED",
                    "fileType": "TO",
                    "diffType": "EFFECTIVE",
                },
            },
            timeout=30,
        )
        if resp.is_success:
            return True
        logger.warning(
            "inline comment failed, posting as general comment",
            file=comment.file_path,
            line=comment.line_number,
            status=resp.status_code,
        )
        _post_comment(
            comments_url, token, f"`{comment.file_path}:{comment.line_number}`\n\n{body}"
        )
        return True
    except Exception as e:
        # Not critical — the finding is already in the summary comment.
        logger.warning(
            "inline comment failed, included in summary",
            file=comment.file_path,
            line=comment.line_number,
            error=str(e),
        )
        return False
