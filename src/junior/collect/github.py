"""GitHub collector backend — enriches context from GitHub API.

Uses shared runbook (git diff + project detection),
then fetches PR description, labels, and comments (issue + inline review) from GitHub REST API.
"""

import structlog

from junior.collect.core import collect_base, enrich_with_metadata
from junior.config import Settings
from junior.github_api import API_BASE, headers as github_headers
from junior.runbooks.code_review.models import CollectedContext, MRComment

logger = structlog.get_logger()

# Cap on how many comments we send to the LLM (newest first).
MAX_COMMENTS = 50


def collect(settings: Settings) -> CollectedContext:
    """Collect context with GitHub PR metadata enrichment."""
    context = collect_base(settings)
    description, labels, comments = _fetch_github_metadata(settings)
    return enrich_with_metadata(context, description, labels, comments)


def _fetch_github_metadata(
    settings: Settings,
) -> tuple[str, list[str], list[MRComment]]:
    """Fetch PR description, labels, and discussion comments from GitHub API."""
    import httpx

    try:
        owner, repo = settings.output.github_repository.split("/", 1)
        pr_number = settings.output.github_event_number

        with httpx.Client(
            timeout=15,
            headers=github_headers(settings.output.github_token),
        ) as client:
            pr_resp = client.get(f"{API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}")
            pr_resp.raise_for_status()
            data = pr_resp.json()
            description = data.get("body") or ""
            labels = [label["name"] for label in data.get("labels", [])]

            issue_comments = _paginate(
                client, f"{API_BASE}/repos/{owner}/{repo}/issues/{pr_number}/comments"
            )
            review_comments = _paginate(
                client, f"{API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}/comments"
            )

        comments = _parse_github_comments(issue_comments, review_comments)
        logger.info(
            "fetched PR metadata from GitHub",
            description_len=len(description),
            comments=len(comments),
        )
        return description, labels, comments
    except Exception as e:
        logger.warning("failed to fetch GitHub PR metadata", error=str(e))
        return "", [], []


def _paginate(client, url: str) -> list[dict]:
    """Walk through paginated GitHub list endpoints (capped at 5 pages × 100 items)."""
    out: list[dict] = []
    next_url: str | None = f"{url}?per_page=100"
    pages = 0
    while next_url and pages < 5:
        resp = client.get(next_url)
        resp.raise_for_status()
        out.extend(resp.json())
        next_url = resp.links.get("next", {}).get("url")
        pages += 1
    return out


def _parse_github_comments(
    issue_comments: list[dict], review_comments: list[dict]
) -> list[MRComment]:
    """Merge general and inline review comments into MRComment list, newest last, capped."""
    parsed: list[MRComment] = []
    for note in issue_comments:
        body = (note.get("body") or "").strip()
        if not body:
            continue
        parsed.append(
            MRComment(
                author=(note.get("user") or {}).get("login") or "",
                body=body,
                created_at=note.get("created_at") or "",
            )
        )
    for note in review_comments:
        body = (note.get("body") or "").strip()
        if not body:
            continue
        parsed.append(
            MRComment(
                author=(note.get("user") or {}).get("login") or "",
                body=body,
                created_at=note.get("created_at") or "",
                file_path=note.get("path"),
                line_number=note.get("line") or note.get("original_line"),
            )
        )

    parsed.sort(key=lambda c: c.created_at)
    if len(parsed) > MAX_COMMENTS:
        parsed = parsed[-MAX_COMMENTS:]
    return parsed
