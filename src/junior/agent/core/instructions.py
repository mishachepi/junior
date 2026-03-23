"""Read project-specific AI instructions (AGENT.md, AGENTS.md, CLAUDE.md)."""

from pathlib import Path

import structlog

logger = structlog.get_logger()

_INSTRUCTION_FILES = ["AGENT.md", "AGENTS.md", "CLAUDE.md"]


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
