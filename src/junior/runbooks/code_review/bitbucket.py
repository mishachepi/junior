"""bitbucket_pr_review — review a Bitbucket DC PR, publish comments to the PR."""

from __future__ import annotations

from junior.config import Settings
from junior.runbooks.code_review.models import CollectedContext, ReviewResult
from junior.runbook.base import EnvVar
from junior.runbook.registry import register_runbook
from junior.runbooks.code_review.base import CodeReviewRunbook


@register_runbook
class BitbucketPrReview(CodeReviewRunbook):
    name = "bitbucket_pr_review"
    description = "review a Bitbucket DC PR → post a comment + inline comments"
    config_fields = CodeReviewRunbook.config_fields + ("bitbucket_url",)
    env_vars = (
        EnvVar("BITBUCKET_URL", True, "base URL of the Bitbucket DC instance (HTTPS)"),
        EnvVar("BITBUCKET_TOKEN", True, "HTTP access token to read/post PR comments"),
        EnvVar("BITBUCKET_PROJECT", True, "project key of the repository"),
        EnvVar("BITBUCKET_REPO", True, "repository slug"),
        EnvVar("BITBUCKET_PR_ID", True, "pull request id (set by your CI, e.g. Jenkins)"),
    )

    def collect(self, settings: Settings) -> CollectedContext:
        from junior.collect.bitbucket import collect

        return collect(settings)

    def _post_to_platform(self, settings: Settings, review: ReviewResult) -> None:
        from junior.publish.bitbucket import post_review

        post_review(settings, review)

    def _publish_requirements(self, settings: Settings) -> list[str]:
        out = settings.output
        errors: list[str] = []
        if not out.bitbucket_url:
            errors.append("BITBUCKET_URL is required to publish to Bitbucket.")
        elif not out.bitbucket_url.startswith("https://"):
            errors.append("BITBUCKET_URL must use HTTPS (the access token is sent as a header).")
        if not out.bitbucket_token:
            errors.append("BITBUCKET_TOKEN (HTTP access token) is required to publish.")
        if not out.bitbucket_project:
            errors.append("BITBUCKET_PROJECT (project key) is required.")
        if not out.bitbucket_repo:
            errors.append("BITBUCKET_REPO (repository slug) is required.")
        if not out.bitbucket_pr_id:
            errors.append("BITBUCKET_PR_ID (pull request id) is required.")
        return errors
