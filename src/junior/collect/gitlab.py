"""GitLab collector backend — enriches context from GitLab API.

Uses shared pipeline (git diff + project detection),
then fetches MR description and labels from GitLab MR API.
"""

import structlog

from junior.collect.core import collect_base, enrich_with_metadata
from junior.config import Settings
from junior.models import CollectedContext

logger = structlog.get_logger()


def collect(settings: Settings) -> CollectedContext:
    """Collect context with GitLab MR metadata enrichment."""
    context = collect_base(settings)
    description, labels = _fetch_gitlab_metadata(settings)
    return enrich_with_metadata(context, description, labels)


def _fetch_gitlab_metadata(settings: Settings) -> tuple[str, list[str]]:
    """Fetch MR description and labels from GitLab API."""
    try:
        import gitlab

        gl = gitlab.Gitlab(settings.ci_server_url, private_token=settings.gitlab_token)
        project = gl.projects.get(settings.ci_project_id)
        mr = project.mergerequests.get(settings.ci_merge_request_iid)

        description = mr.description or ""
        labels = list(mr.labels) if mr.labels else []
        logger.info("fetched MR metadata from GitLab", description_len=len(description))
        return description, labels
    except Exception as e:
        logger.warning("failed to fetch GitLab MR metadata", error=str(e))
        return "", []
