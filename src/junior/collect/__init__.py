"""Phase 1: Deterministic context collection — backend dispatch."""

import structlog

from junior.collect.github import collect as _collect_github
from junior.collect.gitlab import collect as _collect_gitlab
from junior.collect.local import collect as _collect_local
from junior.config import CollectorBackend, Settings
from junior.models import CollectedContext

logger = structlog.get_logger()

_COLLECTORS = {
    CollectorBackend.GITHUB: _collect_github,
    CollectorBackend.GITLAB: _collect_gitlab,
    CollectorBackend.LOCAL: _collect_local,
}


def collect(settings: Settings) -> CollectedContext:
    """Collect all context using the configured collector backend.

    Dispatches to collector module based on settings.resolved_collector enum value.
    Each backend module must export: collect(settings) -> CollectedContext

    Extra context is passed via settings.context (text) and settings.context_files (files).
    """
    context = _COLLECTORS[settings.resolved_collector](settings)

    # Full context as JSON — DEBUG level (can be large for big MRs)
    logger.debug("collected_context", context_json=context.model_dump_json(indent=2))

    return context
