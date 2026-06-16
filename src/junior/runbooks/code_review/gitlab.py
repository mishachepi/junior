"""gitlab_pr_review — review a GitLab MR, publish a note + threads to the MR."""

from __future__ import annotations

from junior.config import Settings
from junior.runbooks.code_review.models import ReviewContext, ReviewResult
from junior.runbook.base import EnvVar
from junior.runbook.registry import register_runbook
from junior.runbooks.code_review.base import CodeReviewRunbook


@register_runbook
class GitlabPrReview(CodeReviewRunbook):
    name = "gitlab_pr_review"
    description = "review a GitLab MR → post a note + inline threads"
    config_fields = CodeReviewRunbook.config_fields + ("ci_server_url",)
    env_vars = (
        EnvVar("GITLAB_TOKEN", True, "api-scoped token to post the MR note"),
        EnvVar("CI_PROJECT_ID", True, "project id (auto in GitLab CI)"),
        EnvVar("CI_MERGE_REQUEST_IID", True, "MR iid (auto in GitLab CI)"),
        EnvVar("CI_MERGE_REQUEST_DIFF_BASE_SHA", False, "enables inline comments (auto in CI)"),
        EnvVar("CI_COMMIT_SHA", False, "enables inline comments (auto in CI)"),
    )

    def collect(self, settings: Settings) -> ReviewContext:
        from junior.collect.gitlab import collect

        return collect(settings)

    def _post_to_platform(self, settings: Settings, review: ReviewResult) -> None:
        from junior.publish.gitlab import post_review

        post_review(settings, review)

    def _publish_requirements(self, settings: Settings) -> list[str]:
        errors: list[str] = []
        if not settings.output.gitlab_token:
            errors.append("GITLAB_TOKEN is required to publish to GitLab.")
        if not settings.output.ci_project_id:
            errors.append("CI_PROJECT_ID is required.")
        if not settings.output.ci_merge_request_iid:
            errors.append("CI_MERGE_REQUEST_IID is required.")
        return errors
