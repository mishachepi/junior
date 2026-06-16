"""Format review results as markdown."""

from __future__ import annotations

from typing import TYPE_CHECKING

from junior.runbooks.code_review.models import ReviewComment, ReviewResult, Severity

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

    output = result.output
    parts = ["## Junior Code Review\n"]
    parts.append(output.summary)
    parts.append("")

    # Findings summary table
    if output.comments:
        parts.append("### Findings")
        parts.append("")
        parts.append("| Severity | Count |")
        parts.append("|----------|-------|")

        for severity in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW):
            count = sum(1 for c in output.comments if c.severity == severity)
            if count > 0:
                emoji = SEVERITY_EMOJI[severity]
                parts.append(f"| {emoji} {severity.value.capitalize()} | {count} |")

        parts.append("")

        # Detailed findings grouped by severity
        for severity in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW):
            comments = [c for c in output.comments if c.severity == severity]
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
    elif output.summary:
        parts.append("No issues found. Great work!")
        parts.append("")

    # Errors
    if result.errors:
        parts.append("### ⚠️ Review Warnings")
        parts.append("")
        for err in result.errors:
            parts.append(f"- {err}")
        parts.append("")

    # Footer
    parts.append("---")
    meta = ["[Junior AI](https://github.com/mishachepi/junior/)"]
    if settings:
        meta.append(settings.llm.harness_name)
        if settings.llm.display_model:
            meta.append(settings.llm.display_model)
    usage = result.usage
    if usage.input_tokens or usage.output_tokens:
        meta.append(f"{usage.input_tokens:,} in / {usage.output_tokens:,} out tokens")
    elif usage.total_tokens:
        meta.append(f"{usage.total_tokens:,} tokens")
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
