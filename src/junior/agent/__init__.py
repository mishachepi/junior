"""Phase 2: AI review — backend dispatch."""

import importlib

import structlog

from junior.config import Settings
from junior.models import CollectedContext, ReviewResult
from junior.prompt_loader import Prompt

logger = structlog.get_logger()


def review(
    context: CollectedContext,
    settings: Settings,
    prompts: list[Prompt],
) -> ReviewResult:
    """Run AI review using the configured backend.

    Dispatches to agent module based on settings.agent_backend enum value.
    Each backend module must export: review(context, settings, prompts) -> ReviewResult
    """
    module = importlib.import_module(settings.agent_backend.value)
    result = module.review(context, settings, prompts)

    logger.debug("review_result", result_json=result.model_dump_json(indent=2))

    return result
