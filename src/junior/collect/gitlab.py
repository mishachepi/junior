"""GitLab collector backend — enriches context from GitLab API.

Uses shared runbook (git diff + project detection),
then fetches MR description, labels, and discussion comments from GitLab MR API.
"""

import structlog

from junior.collect.core import collect_base, enrich_with_metadata
from junior.config import Settings
from junior.runbooks.code_review.models import CollectedContext, MRComment

logger = structlog.get_logger()

# Cap on how many human comments we send to the LLM (newest first).
MAX_COMMENTS = 50


def collect(settings: Settings) -> CollectedContext:
    """Collect context with GitLab MR metadata enrichment."""
    context = collect_base(settings)
    description, labels, comments = _fetch_gitlab_metadata(settings)
    return enrich_with_metadata(context, description, labels, comments)


def _fetch_gitlab_metadata(
    settings: Settings,
) -> tuple[str, list[str], list[MRComment]]:
    """Fetch MR description, labels, and discussion comments from GitLab API."""
    out = settings.output
    if out.gitlab_token and not out.ci_server_url.lower().startswith("https://"):
        # Warn but keep going — local/intranet HTTP instances stay usable.
        logger.warning(
            "CI_SERVER_URL is not HTTPS — the private token is sent in cleartext",
            url=out.ci_server_url,
        )
    try:
        import gitlab

        gl = gitlab.Gitlab(
            settings.output.ci_server_url, private_token=settings.output.gitlab_token
        )
        project = gl.projects.get(settings.output.ci_project_id)
        mr = project.mergerequests.get(settings.output.ci_merge_request_iid)

        description = mr.description or ""
        labels = list(mr.labels) if mr.labels else []
        comments = _fetch_gitlab_comments(mr)
        logger.info(
            "fetched MR metadata from GitLab",
            description_len=len(description),
            comments=len(comments),
        )
        return description, labels, comments
    except Exception as e:
        logger.warning("failed to fetch GitLab MR metadata", error=str(e))
        return "", [], []


def _fetch_gitlab_comments(mr) -> list[MRComment]:
    """Fetch all human discussion notes (including inline) for an MR.

    System notes ("assigned", "added label X", ...) are filtered out.
    Returns at most MAX_COMMENTS newest entries.
    """
    try:
        discussions = mr.discussions.list(get_all=True)
    except Exception as e:
        logger.warning("failed to fetch GitLab MR discussions", error=str(e))
        return []

    parsed: list[MRComment] = []
    for discussion in discussions:
        resolved = bool(discussion.attributes.get("resolved", False) if hasattr(discussion, "attributes") else False)
        notes = discussion.attributes.get("notes", []) if hasattr(discussion, "attributes") else []
        for note in notes:
            if note.get("system"):
                continue
            body = (note.get("body") or "").strip()
            if not body:
                continue
            author = (note.get("author") or {}).get("username") or (note.get("author") or {}).get("name") or ""
            position = note.get("position") or {}
            file_path = position.get("new_path") or position.get("old_path")
            line_number = position.get("new_line") or position.get("old_line")
            parsed.append(
                MRComment(
                    author=author,
                    body=body,
                    created_at=note.get("created_at") or "",
                    file_path=file_path,
                    line_number=line_number,
                    resolved=bool(note.get("resolved", resolved)),
                )
            )

    parsed.sort(key=lambda c: c.created_at)
    if len(parsed) > MAX_COMMENTS:
        parsed = parsed[-MAX_COMMENTS:]
    return parsed
