"""Shared Bitbucket Data Center REST API (1.0) helpers used by both
`collect.bitbucket` and `publish.bitbucket`.

Auth is an HTTP access token sent as a Bearer header (no basic auth); the
instance should be reached over HTTPS only — `bitbucket_pr_review.validate()`
enforces that when publishing.
"""

from __future__ import annotations


def pr_api_base(url: str, project: str, repo: str, pr_id: int | None) -> str:
    """Base API path for one pull request on a Bitbucket DC instance."""
    return (
        f"{url.rstrip('/')}/rest/api/1.0/projects/{project}"
        f"/repos/{repo}/pull-requests/{pr_id}"
    )


def headers(token: str) -> dict[str, str]:
    """Authorization + Accept headers for a Bitbucket DC REST request."""
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
