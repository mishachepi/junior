"""GitHub collector backend — enriches context from GitHub API.

Uses shared pipeline (git diff + project detection),
then fetches PR description and labels from GitHub REST API.
"""

import structlog

from junior.collect.core import collect_base, enrich_with_metadata
from junior.config import Settings
from junior.models import CollectedContext

logger = structlog.get_logger()

_API_BASE = "https://api.github.com"


def collect(settings: Settings) -> CollectedContext:
    """Collect context with GitHub PR metadata enrichment."""
    context = collect_base(settings)
    description, labels = _fetch_github_metadata(settings)
    return enrich_with_metadata(context, description, labels)


def _fetch_github_metadata(settings: Settings) -> tuple[str, list[str]]:
    """Fetch PR description and labels from GitHub API."""
    try:
        import httpx

        owner, repo = settings.github_repository.split("/", 1)
        resp = httpx.get(
            f"{_API_BASE}/repos/{owner}/{repo}/pulls/{settings.github_event_number}",
            headers={
                "Authorization": f"Bearer {settings.github_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        description = data.get("body") or ""
        labels = [label["name"] for label in data.get("labels", [])]
        logger.info("fetched PR metadata from GitHub", description_len=len(description))
        return description, labels
    except Exception as e:
        logger.warning("failed to fetch GitHub PR metadata", error=str(e))
        return "", []
