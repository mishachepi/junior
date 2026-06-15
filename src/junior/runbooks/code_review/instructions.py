"""Shared instructions and prompt building for agent backends."""

from __future__ import annotations

from pathlib import Path

import structlog

logger = structlog.get_logger()

_INSTRUCTION_FILES = ["AGENT.md", "AGENTS.md", "CLAUDE.md"]

# Project instructions are inlined into every review's system prompt. A huge
# AGENT.md/CLAUDE.md would crowd out the diff and inflate every call, so it is
# truncated beyond this size (with a warning — trim the file or use --prompt-file
# for a curated review prompt instead).
MAX_INSTRUCTIONS_CHARS = 30_000

BASE_RULES = """
## Rules
- Only report issues you are confident about
- Focus on the CHANGED code (the diff), not pre-existing issues
- Provide actionable suggestions with each finding
- Be constructive, not pedantic
- If the code looks good, say so — don't invent issues
- Use "request_changes" only for critical or multiple high-severity issues
- Use "approve" when the code is good or has only minor suggestions

## Severity Levels
Severity reflects user/system impact, not the issue category. A "bug" can be any severity.
- **critical** — data loss, security breach, crashes in production, silent data corruption, auth bypass
- **high** — incorrect behavior affecting users, resource leaks under normal usage, broken error handling that hides failures, accumulating memory leaks
- **medium** — edge case bugs, performance issues under realistic load, misleading API contracts, recoverable failures with poor UX
- **low** — code clarity, minor DRY violations, naming inconsistencies, theoretical issues unlikely to trigger

You can explore the repository files for additional context if needed.
"""


def build_review_prompt(head: str, project_dir: str) -> str:
    """Append the shared review rules + project instructions to `head` (the
    runbook's role plus any user prompts).

    Built once per run by `CodeReviewRunbook.system_prompt()` and passed
    unchanged to whatever harness is selected — every harness gets the same
    system prompt; only the user message varies by `file_access`.
    """
    parts = [head, BASE_RULES]

    project_instructions = read_project_instructions(project_dir)
    if project_instructions:
        parts.append(f"## Project-Specific Instructions\n{project_instructions}")

    return "\n\n".join(p.strip() for p in parts if p.strip())


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
            except OSError as e:
                logger.warning("failed to read project instructions", file=filename, error=str(e))
                continue
            if len(content) > MAX_INSTRUCTIONS_CHARS:
                logger.warning(
                    "project instructions truncated",
                    file=filename,
                    length=len(content),
                    max_chars=MAX_INSTRUCTIONS_CHARS,
                )
                content = (
                    content[:MAX_INSTRUCTIONS_CHARS]
                    + "\n\n[...truncated by junior — file exceeds the prompt budget]"
                )
            logger.debug("loaded project instructions", file=filename, length=len(content))
            return content
    return None
