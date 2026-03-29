"""Shared instructions and prompt building for agent backends."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from junior.prompt_loader import Prompt

logger = structlog.get_logger()

_INSTRUCTION_FILES = ["AGENT.md", "AGENTS.md", "CLAUDE.md"]

BASE_RULES = """
## Rules
- Only report issues you are confident about
- Focus on the CHANGED code (the diff), not pre-existing issues
- Provide actionable suggestions with each finding
- Be constructive, not pedantic
- If the code looks good, say so — don't invent issues
- Use "request_changes" only for critical or multiple high-severity issues
- Use "approve" when the code is good or has only minor suggestions

You can explore the repository files for additional context if needed.
"""


def build_review_prompt(prompts: list[Prompt], project_dir: str) -> str:
    """Build system/review prompt: prompt bodies + rules + project instructions.

    Shared by codex and claudecode backends.
    """
    parts: list[str] = []
    for p in prompts:
        parts.append(f"## Analysis: {p.name}")
        parts.append(p.body)
        parts.append("")

    parts.append(BASE_RULES)

    project_instructions = read_project_instructions(project_dir)
    if project_instructions:
        parts.append(f"## Project-Specific Instructions\n{project_instructions}\n")

    return "\n".join(parts)


def read_project_instructions(project_dir: str) -> str | None:
    """Read project-specific AI instructions from repo root.

    Searches for AGENT.md → AGENTS.md → CLAUDE.md in priority order.
    Returns file content or None if not found.
    """
    root = Path(project_dir).resolve()
    for filename in _INSTRUCTION_FILES:
        path = root / filename
        if path.is_file():
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                logger.info("loaded project instructions", file=filename, length=len(content))
                return content
            except OSError as e:
                logger.warning("failed to read project instructions", file=filename, error=str(e))
                continue
    return None
