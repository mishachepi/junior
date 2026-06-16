"""Core collection runbook and shared libraries.

Exports the main runbook (collect_base, enrich_with_metadata)
used by all collector backends.
"""

from junior.collect.core.collect import collect_base, enrich_with_metadata
from junior.collect.core.comments import MAX_COMMENTS, finalize_comments

__all__ = [
    "MAX_COMMENTS",
    "collect_base",
    "enrich_with_metadata",
    "finalize_comments",
]
