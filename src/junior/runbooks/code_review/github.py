"""github_pr_review — review a GitHub PR, publish review comments to the PR."""

from __future__ import annotations

from junior.config import Settings
from junior.runbooks.code_review.models import CollectedContext, ReviewResult
from junior.runbook.base import EnvVar
from junior.runbook.registry import register_runbook
from junior.runbooks.code_review.base import CodeReviewRunbook


@register_runbook
class GithubPrReview(CodeReviewRunbook):
    name = "github_pr_review"
    description = "review a GitHub PR → post review comments"
    env_vars = (
        EnvVar("GITHUB_TOKEN", True, "auth to post PR review comments"),
        EnvVar("GITHUB_REPOSITORY", True, "owner/repo (auto in GitHub Actions)"),
        EnvVar("GITHUB_EVENT_NUMBER", True, "the PR number (map from the event payload)"),
        EnvVar("GITHUB_EVENT_BEFORE", False, "diff only the new commits on a push"),
    )

    def collect(self, settings: Settings) -> CollectedContext:
        from junior.collect.github import collect

        return collect(settings)

    def _post_to_platform(self, settings: Settings, review: ReviewResult) -> None:
        from junior.publish.github import post_review

        post_review(settings, review)

    def _publish_requirements(self, settings: Settings) -> list[str]:
        errors: list[str] = []
        if not settings.output.github_token:
            errors.append("GITHUB_TOKEN is required to publish to GitHub.")
        if not settings.output.github_repository:
            errors.append("GITHUB_REPOSITORY is required.")
        if not settings.output.github_event_number:
            errors.append("GITHUB_EVENT_NUMBER (PR number) is required.")
        return errors
