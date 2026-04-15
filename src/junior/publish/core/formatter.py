"""Format review results as markdown."""

from __future__ import annotations

from typing import TYPE_CHECKING

from junior.models import ReviewComment, ReviewResult, Severity

if TYPE_CHECKING:
    from junior.config import Settings


SEVERITY_EMOJI = {
    Severity.CRITICAL: "🔴",
    Severity.HIGH: "🟠",
    Severity.MEDIUM: "🟡",
    Severity.LOW: "🟢",
}


def format_summary(result: ReviewResult, settings: Settings | None = None) -> str:
    """Format the full review as markdown."""
    if result.pre_formatted:
        return result.pre_formatted

    parts = ["## Junior Code Review\n"]
    parts.append(result.summary)
    parts.append("")

    # Findings summary table
    if result.comments:
        parts.append("### Findings")
        parts.append("")
        parts.append("| Severity | Count |")
        parts.append("|----------|-------|")

        for severity in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW):
            count = sum(1 for c in result.comments if c.severity == severity)
            if count > 0:
                emoji = SEVERITY_EMOJI[severity]
                parts.append(f"| {emoji} {severity.value.capitalize()} | {count} |")

        parts.append("")

        # Detailed findings grouped by severity
        for severity in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW):
            comments = [c for c in result.comments if c.severity == severity]
            if not comments:
                continue

            emoji = SEVERITY_EMOJI[severity]
            parts.append(f"#### {emoji} {severity.value.capitalize()}")
            parts.append("")

            for c in comments:
                location = ""
                if c.file_path:
                    location = f" `{c.file_path}"
                    if c.line_number:
                        location += f":{c.line_number}"
                    location += "`"

                parts.append(f"- **[{c.category.value}]**{location} — {c.message}")
                if c.suggestion:
                    parts.append(f"  - Suggestion: {c.suggestion}")

            parts.append("")
    elif result.summary:
        parts.append("No issues found. Great work!")
        parts.append("")

    # Errors
    if result.review_errors:
        parts.append("### ⚠️ Review Warnings")
        parts.append("")
        for err in result.review_errors:
            parts.append(f"- {err}")
        parts.append("")

    # Footer
    parts.append("---")
    meta = ["[Junior AI](https://github.com/mishachepi/junior/)"]
    if settings:
        meta.append(settings.agent_backend.name.lower())
    if result.tokens_used:
        meta.append(f"{result.tokens_used:,} tokens")
    parts.append(f"*Reviewed by {' | '.join(meta)}*")

    return "\n".join(parts)


def format_inline_comment(comment: ReviewComment) -> str:
    """Format a single inline comment for a discussion thread."""
    emoji = SEVERITY_EMOJI.get(comment.severity, "")
    parts = [f"{emoji} **{comment.severity.value.upper()}** [{comment.category.value}]"]
    parts.append("")
    parts.append(comment.message)

    if comment.suggestion:
        parts.append("")
        parts.append(f"**Suggestion:** {comment.suggestion}")

    return "\n".join(parts)
