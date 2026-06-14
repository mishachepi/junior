"""Local collector backend — no platform API enrichment.

Uses shared runbook (git diff + project detection). MR metadata comes
from environment variables or CLI args only (no API calls).
"""

from junior.collect.core import collect_base
from junior.config import Settings
from junior.runbooks.code_review.models import CollectedContext


def collect(settings: Settings) -> CollectedContext:
    """Collect context locally without any platform API calls."""
    return collect_base(settings)
