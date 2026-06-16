"""Bitbucket Data Center collector backend — enriches context from the REST API.

Uses shared runbook (git diff + project detection), then fetches PR title,
description, and discussion comments from the Bitbucket DC 1.0 REST API.
The diff itself stays local (git); the API supplies metadata only — including
`toRef.latestCommit`, used as the diff base when none is set explicitly
(Bitbucket DC has no CI of its own, so there is no auto base-SHA variable).
"""

from datetime import UTC, datetime

import structlog

from junior.bitbucket_api import headers as bitbucket_headers, pr_api_base
from junior.collect.core import collect_base, enrich_with_metadata, finalize_comments
from junior.config import Settings
from junior.runbooks.code_review.models import ReviewContext, MRComment

logger = structlog.get_logger()

# Pagination cap for the activities feed (pages × 100 items).
MAX_ACTIVITY_PAGES = 5


def collect(settings: Settings) -> ReviewContext:
    """Collect context with Bitbucket DC PR metadata enrichment."""
    title, description, base_sha, comments = _fetch_bitbucket_metadata(settings)
    if base_sha and not settings.context.base_sha:
        # The PR's target tip is the diff base — same role CI_MERGE_REQUEST_DIFF_BASE_SHA
        # plays for GitLab, but resolved from the API instead of a CI variable.
        settings = settings.model_copy(
            update={"context": settings.context.model_copy(update={"base_sha": base_sha})}
        )
    context = collect_base(settings)
    if title and not context.mr_title:
        context = context.model_copy(update={"mr_title": title})
    return enrich_with_metadata(context, description, [], comments)


def _fetch_bitbucket_metadata(
    settings: Settings,
) -> tuple[str, str, str | None, list[MRComment]]:
    """Fetch PR title, description, base SHA, and comments from the Bitbucket API."""
    import httpx

    out = settings.output
    if out.bitbucket_url and not out.bitbucket_url.lower().startswith("https://"):
        # Publishing hard-fails on non-HTTPS (_publish_requirements); collect
        # only warns so read-only runs against an intranet instance still work.
        logger.warning(
            "BITBUCKET_URL is not HTTPS — the access token is sent in cleartext",
            url=out.bitbucket_url,
        )
    try:
        api_base = pr_api_base(
            out.bitbucket_url, out.bitbucket_project, out.bitbucket_repo, out.bitbucket_pr_id
        )
        with httpx.Client(
            timeout=15,
            headers=bitbucket_headers(out.bitbucket_token),
        ) as client:
            pr_resp = client.get(api_base)
            pr_resp.raise_for_status()
            data = pr_resp.json()
            title = data.get("title") or ""
            description = data.get("description") or ""
            base_sha = (data.get("toRef") or {}).get("latestCommit")

            activities = _paginate_activities(client, f"{api_base}/activities")

        comments = _parse_bitbucket_comments(activities)
        logger.info(
            "fetched PR metadata from Bitbucket",
            description_len=len(description),
            comments=len(comments),
        )
        return title, description, base_sha, comments
    except Exception as e:
        logger.warning("failed to fetch Bitbucket PR metadata", error=str(e))
        return "", "", None, []


def _paginate_activities(client, url: str) -> list[dict]:
    """Walk Bitbucket's start/isLastPage/nextPageStart pagination (capped)."""
    out: list[dict] = []
    start = 0
    for _ in range(MAX_ACTIVITY_PAGES):
        resp = client.get(url, params={"start": start, "limit": 100})
        resp.raise_for_status()
        page = resp.json()
        out.extend(page.get("values", []))
        if page.get("isLastPage", True):
            break
        next_start = page.get("nextPageStart")
        if next_start is None:
            break
        start = next_start
    return out


def _parse_bitbucket_comments(activities: list[dict]) -> list[MRComment]:
    """Flatten COMMENTED activities (incl. nested reply threads) into MRComments.

    Other activity types (APPROVED, MERGED, RESCOPED, ...) are filtered out.
    Returns at most MAX_COMMENTS newest entries (see `finalize_comments`).
    """
    parsed: list[MRComment] = []
    for activity in activities:
        if activity.get("action") != "COMMENTED":
            continue
        comment = activity.get("comment") or {}
        anchor = activity.get("commentAnchor") or {}
        _collect_comment_thread(comment, anchor, parsed)

    return finalize_comments(parsed)


def _collect_comment_thread(comment: dict, anchor: dict, out: list[MRComment]) -> None:
    """Append one comment plus its nested replies (`comment.comments`).

    Replies share the thread root's anchor — Bitbucket anchors the thread,
    not each reply individually.
    """
    body = (comment.get("text") or "").strip()
    if body:
        author = (comment.get("author") or {}).get("name") or ""
        out.append(
            MRComment(
                author=author,
                body=body,
                created_at=_format_timestamp(comment.get("createdDate")),
                file_path=anchor.get("path"),
                line_number=anchor.get("line"),
                resolved=comment.get("state") == "RESOLVED",
            )
        )
    for reply in comment.get("comments") or []:
        _collect_comment_thread(reply, anchor, out)


def _format_timestamp(ms: int | None) -> str:
    """Bitbucket sends epoch milliseconds; normalize to sortable ISO-8601."""
    if not ms:
        return ""
    return datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat()
