"""Core collection pipeline and shared libraries.

Exports the main pipeline (collect_base, enrich_with_metadata)
used by all collector backends.
"""

from junior.collect.core.collect import collect_base, enrich_with_metadata

__all__ = [
    "collect_base",
    "enrich_with_metadata",
]
