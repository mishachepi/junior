"""Phase 2: AI review — backend dispatch."""

import structlog

from junior.agent.claudecode import review as _review_claudecode
from junior.agent.codex import review as _review_codex
from junior.agent.deepagents import review as _review_deepagents
from junior.agent.pydantic import review as _review_pydantic
from junior.config import AgentBackend, Settings
from junior.models import CollectedContext, ReviewResult
from junior.prompt_loader import Prompt

logger = structlog.get_logger()

_AGENTS = {
    AgentBackend.PYDANTIC: _review_pydantic,
    AgentBackend.CODEX: _review_codex,
    AgentBackend.CLAUDECODE: _review_claudecode,
    AgentBackend.DEEPAGENTS: _review_deepagents,
}


def review(
    context: CollectedContext,
    settings: Settings,
    prompts: list[Prompt],
) -> ReviewResult:
    """Run AI review using the configured backend.

    Dispatches to agent module based on settings.agent_backend enum value.
    Each backend module must export: review(context, settings, prompts) -> ReviewResult
    """
    result = _AGENTS[settings.agent_backend](context, settings, prompts)

    logger.debug("review_result", result_json=result.model_dump_json(indent=2))

    return result
