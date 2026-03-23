"""Phase 1: Deterministic context collection — backend dispatch."""

import importlib

import structlog

from junior.config import Settings
from junior.models import CollectedContext

logger = structlog.get_logger()


def collect(settings: Settings) -> CollectedContext:
    """Collect all context using the configured collector backend.

    Dispatches to collector module based on settings.resolved_collector enum value.
    Each backend module must export: collect(settings) -> CollectedContext

    Extra context is passed via settings.context (text) and settings.context_files (files).
    """
    module = importlib.import_module(settings.resolved_collector.value)
    context = module.collect(settings)

    # Full context as JSON — DEBUG level (can be large for big MRs)
    logger.debug("collected_context", context_json=context.model_dump_json(indent=2))

    return context
