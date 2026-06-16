"""CodeReviewRunbook — shared base for the code-review runbook family.

`local_review`, `github_pr_review`, `gitlab_pr_review` all review a git diff with
the same context schema, render, prompt, and result schema. Only *where the diff
comes from* (collect) and *where the review goes* (publish) differ — those are the
per-platform subclasses. This base holds everything else so the variants stay
tiny. It is not registered (abstract `collect`/`_post_to_platform`).
"""

from __future__ import annotations

import structlog

from junior.config import Settings
from junior.runbooks.code_review.models import (
    CollectedContext,
    LLMReviewOutput,
    Recommendation,
    ReviewResult,
    Severity,
    assemble_review_result,
)
from junior.runbook.base import Runbook, Usage

logger = structlog.get_logger()


# A diff up to this size is inlined into the user message even for engines
# with their own file access (claudecode/codex). The diff is the review's
# primary evidence: a file-reading engine sees only the *final* file state, so
# a regression visible only in the dropped lines (e.g. a safe call replaced by
# an unsafe one) reads as pre-existing code and gets skipped. ~50k chars ≈ 12k
# tokens — cheap insurance; above that, engines fall back to their file tools.
INLINE_DIFF_MAX_CHARS = 50_000


class CodeReviewRunbook(Runbook[CollectedContext, LLMReviewOutput]):
    context_model = CollectedContext
    result_model = LLMReviewOutput
    needs_git = True  # every code-review variant diffs a local git repo
    # Diff/collection settings every code-review variant honours.
    config_fields = ("source", "base_sha", "target_branch", "max_file_size", "max_diff_chars")
    SYSTEM_PROMPT = (
        "You are a senior code reviewer. Review the diff in the context of the "
        "surrounding codebase and report concise, actionable findings tied to the diff "
        "— prioritising correctness, security, data-integrity and API-contract regressions."
    )

    # --- shared domain logic (same for every platform) ---

    def render(self, context: CollectedContext, settings: Settings, *, file_access: bool) -> str:
        from junior.runbooks.code_review.render import build_user_message

        # SDK engines (pydantic/deepagents) always get the diff inlined.
        # File-access engines (claudecode/codex) get it too while it's small —
        # only an oversized diff falls back to "read the files yourself".
        include_diff = not file_access or len(context.full_diff) <= INLINE_DIFF_MAX_CHARS
        # `max_diff_chars` is a separate, harder cap: whenever the diff *is*
        # inlined, truncate it so even an SDK engine can't be handed millions
        # of tokens (0 = no cap).
        return build_user_message(
            context,
            include_diff=include_diff,
            max_diff_chars=settings.context.max_diff_chars,
        )

    def system_prompt(self, settings: Settings) -> str:
        from junior.prompt_loader import merge_prompts
        from junior.runbooks.code_review.instructions import build_review_prompt

        # role + user prompts, then the shared review rules.
        head = merge_prompts(self.SYSTEM_PROMPT, list(settings.context.prompts))
        return build_review_prompt(head)

    def is_blocking(self, result: LLMReviewOutput) -> bool:
        critical = any(c.severity == Severity.CRITICAL for c in result.comments)
        return critical or result.recommendation == Recommendation.REQUEST_CHANGES

    def is_empty(self, context: CollectedContext) -> bool:
        return not context.full_diff

    def summary(self, result: LLMReviewOutput) -> dict:
        critical = sum(1 for c in result.comments if c.severity == Severity.CRITICAL)
        high = sum(1 for c in result.comments if c.severity == Severity.HIGH)
        return {
            "findings": len(result.comments),
            "critical": critical or None,
            "high": high or None,
            "recommendation": result.recommendation.value,
        }

    # --- publish: local always; platform when enabled (template method) ---

    def publish(
        self,
        settings: Settings,
        result: LLMReviewOutput,
        usage: Usage,
        *,
        errors: list[str],
    ) -> None:
        # Only runs with --publish. local_review renders the pretty Markdown
        # locally; github/gitlab post to the platform (see `_post_to_platform`).
        review = assemble_review_result(
            result,
            tokens_used=usage.total_tokens,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            review_errors=errors,
        )
        self._post_to_platform(settings, review)

    def publish_prepared(self, settings: Settings, markdown: str) -> None:
        """Post a pre-generated `.md` to the platform (for --publish-file)."""
        self._post_to_platform(
            settings, ReviewResult(summary="pre-generated", pre_formatted=markdown)
        )

    def validate(self, settings: Settings, *, publish_enabled: bool) -> list[str]:
        return self._publish_requirements(settings) if publish_enabled else []

    # --- per-platform hooks (subclasses implement) ---

    def _post_to_platform(self, settings: Settings, review: ReviewResult) -> None:
        raise NotImplementedError

    def _publish_requirements(self, settings: Settings) -> list[str]:
        """Config keys this runbook needs in order to publish."""
        return []
