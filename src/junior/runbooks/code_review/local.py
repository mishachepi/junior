"""local_review — review the local git diff, output to stdout/file. No platform."""

from __future__ import annotations

from junior.config import Settings
from junior.runbooks.code_review.models import ReviewContext, ReviewResult
from junior.runbook.registry import register_runbook
from junior.runbooks.code_review.base import CodeReviewRunbook


@register_runbook
class LocalReview(CodeReviewRunbook):
    name = "local_review"
    description = "review the local git diff → raw JSON, or --publish for Markdown"

    def collect(self, settings: Settings) -> ReviewContext:
        from junior.collect.local import collect

        return collect(settings)

    def _post_to_platform(self, settings: Settings, review: ReviewResult) -> None:
        # No platform — `--publish` means "render the pretty Markdown review"
        # to stdout (redirect with `>` to save). Without --publish you get raw JSON.
        from junior.publish.local import post_review

        post_review(settings, review)

    def output_destination(self, settings: Settings, *, publish_enabled: bool) -> str:
        if publish_enabled:
            return "stdout"  # rendered Markdown; redirect with `>` for a file
        return settings.output.output_file or "stdout"
