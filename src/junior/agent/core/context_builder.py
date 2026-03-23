"""Build user message from CollectedContext for all agent backends."""

import structlog

from junior.models import CollectedContext

logger = structlog.get_logger()


def build_user_message(context: CollectedContext, *, include_diff: bool = True) -> str:
    """Build user message with full MR context for AI agents.

    Used by all backends (pydantic, deepagents, codex).
    When include_diff=False (codex), omits the full diff and adds
    file-tool instructions instead — codex reads files via sandbox.
    """
    parts = []

    if context.mr_title:
        parts.append(f"## Merge Request: {context.mr_title}")
    if context.mr_description:
        parts.append(f"**Description:** {context.mr_description}")

    if context.source_branch or context.target_branch:
        parts.append(f"**Branches:** {context.source_branch} → {context.target_branch}")
    if context.labels:
        parts.append(f"**Labels:** {', '.join(context.labels)}")
    parts.append("")

    # Extra context from --context and --context-file
    if context.extra_context:
        parts.append("### Additional Context")
        for key, value in context.extra_context.items():
            parts.append(f"#### {key}")
            parts.append(value)
            parts.append("")

    # Commit messages
    if context.commit_messages:
        parts.append(f"### Commits ({len(context.commit_messages)})")
        for msg in context.commit_messages:
            parts.append(f"- {msg}")
        parts.append("")

    # Changed files list
    parts.append("### Changed Files")
    if not include_diff:
        parts.append("Review these files using your file tools:")
        parts.append("")
    for f in context.changed_files:
        if include_diff:
            parts.append(f"- `{f.path}` ({f.status.value})")
        else:
            lines_added = sum(1 for l in f.diff.splitlines() if l.startswith("+") and not l.startswith("+++")) if f.diff else 0
            lines_removed = sum(1 for l in f.diff.splitlines() if l.startswith("-") and not l.startswith("---")) if f.diff else 0
            parts.append(f"- `{f.path}` ({f.status.value}) +{lines_added}/-{lines_removed}")
    parts.append("")

    if include_diff:
        parts.append("### Diff")
        parts.append("```diff")
        parts.append(context.full_diff)
        parts.append("```")
    else:
        parts.append(f"**Total diff size:** {len(context.full_diff)} chars across {len(context.changed_files)} files")
        parts.append("")
        parts.append("Use your file reading tools to inspect the changed files listed above. Focus your review on the changes, not pre-existing code.")

    message = "\n".join(parts)
    logger.info(
        "built user message for AI",
        message_size=len(message),
        changed_files=len(context.changed_files),
        diff_size=len(context.full_diff),
        extra_context_keys=list(context.extra_context.keys()) or None,
    )
    return message
