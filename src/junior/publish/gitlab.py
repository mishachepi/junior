"""GitLab API integration: post review results to MR."""

import structlog

from junior.config import Settings
from junior.runbooks.code_review.models import ReviewComment, ReviewResult
from junior.publish.core import MAX_INLINE_COMMENTS, format_inline_comment, format_summary

logger = structlog.get_logger()


def post_review(settings: Settings, result: ReviewResult) -> None:
    """Post review results to GitLab MR."""
    import gitlab

    out = settings.output
    if out.gitlab_token and not out.ci_server_url.lower().startswith("https://"):
        # Warn but keep going — local/intranet HTTP instances stay usable.
        logger.warning(
            "CI_SERVER_URL is not HTTPS — the private token is sent in cleartext",
            url=out.ci_server_url,
        )

    gl = gitlab.Gitlab(
        settings.output.ci_server_url, private_token=settings.output.gitlab_token
    )
    project = gl.projects.get(settings.output.ci_project_id)
    mr = project.mergerequests.get(settings.output.ci_merge_request_iid)

    # Post summary note
    summary = format_summary(result, settings=settings)
    mr.notes.create({"body": summary})
    logger.info(
        "posted summary note",
        project_id=settings.output.ci_project_id,
        mr_iid=settings.output.ci_merge_request_iid,
    )

    # Post inline comments as discussion threads
    base_sha = settings.output.ci_merge_request_diff_base_sha
    head_sha = settings.output.ci_commit_sha
    if not base_sha or not head_sha:
        logger.info(
            "no SHAs available, skipping inline comments",
            base_sha=bool(base_sha),
            head_sha=bool(head_sha),
        )
        return

    inline_comments = [c for c in result.comments if c.file_path and c.line_number]
    posted = 0

    for comment in inline_comments[:MAX_INLINE_COMMENTS]:
        if _post_inline_comment(mr, comment, base_sha or head_sha, head_sha):
            posted += 1

    if posted:
        logger.info("posted inline comments", count=posted)


def _post_inline_comment(mr, comment: ReviewComment, base_sha: str, head_sha: str) -> bool:
    """Post a single inline comment as a discussion thread. Returns True on success."""
    body = format_inline_comment(comment)

    try:
        mr.discussions.create(
            {
                "body": body,
                "position": {
                    "base_sha": base_sha,
                    "start_sha": base_sha,
                    "head_sha": head_sha,
                    "position_type": "text",
                    "new_path": comment.file_path,
                    "new_line": comment.line_number,
                },
            }
        )
        return True
    except Exception as e:
        # Inline comment failed — not critical, already in summary
        logger.warning(
            "inline comment failed, included in summary",
            file=comment.file_path,
            line=comment.line_number,
            error=str(e),
        )
        return False
