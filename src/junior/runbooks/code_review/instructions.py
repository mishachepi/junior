"""Shared instructions and prompt building for agent backends."""

from __future__ import annotations

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


def build_review_prompt(head: str) -> str:
    """Append the shared review rules to `head` (the runbook's role plus any
    user prompts).

    Built once per run by `CodeReviewRunbook.system_prompt()` and passed
    unchanged to whatever harness is selected — every harness gets the same
    system prompt; only the user message varies by `file_access`.

    Project instruction files (AGENT.md/AGENTS.md/CLAUDE.md) are deliberately
    *not* inlined here: the diff's author controls them, so doing so would let
    a reviewed branch rewrite the reviewer's instructions. A harness that wants
    project memory reads it itself from its own cwd (claudecode → CLAUDE.md,
    codex → AGENTS.md).
    """
    parts = [head, BASE_RULES]
    return "\n\n".join(p.strip() for p in parts if p.strip())
