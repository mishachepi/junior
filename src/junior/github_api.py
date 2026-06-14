"""Shared GitHub REST API constants and helpers used by both
`collect.github` and `publish.github`.
"""

from __future__ import annotations


API_BASE = "https://api.github.com"


def headers(token: str) -> dict[str, str]:
    """Authorization + Accept headers for a GitHub REST request."""
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
