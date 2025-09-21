"""GitHub integration service."""

import httpx
import structlog

from ..config import settings
from .github_client import GitHubClient

logger = structlog.get_logger(__name__)


class GitHubService:
    """Service for GitHub API operations."""

    def __init__(self):
        self.logger = logger.bind(component="GitHubService")
        self._client = None

    def _get_client(self) -> GitHubClient:
        """Get GitHub client instance."""
        if not settings.github_token:
            raise ValueError("GitHub token is required")
        if not self._client:
            self._client = GitHubClient()
        return self._client

    async def get_pr_diff(self, repository: str, pr_number: int) -> str:
        """Get the diff content for a PR."""
        try:
            # Get PR data
            github_client = self._get_client()
            pr_data = await github_client.get_pull_request(repository, pr_number)

            # Fetch diff content with proper authentication
            headers = {
                "Accept": "application/vnd.github.v3.diff",
                "User-Agent": "Junior-AI-Review-Agent/1.0",
            }

            # Add GitHub token for authentication
            if settings.github_token:
                headers["Authorization"] = f"token {settings.github_token}"

            async with httpx.AsyncClient(timeout=30.0) as client:
                # Use the PR's diff URL from GitHub API
                diff_url = (
                    pr_data.get("diff_url")
                    or f"https://api.github.com/repos/{repository}/pulls/{pr_number}.diff"
                )

                response = await client.get(diff_url, headers=headers)
                response.raise_for_status()
                return response.text

        except Exception as e:
            self.logger.error(
                "Failed to get PR diff", repo=repository, pr=pr_number, error=str(e)
            )
            raise

    async def post_review_to_github(
        self, repository: str, pr_number: int, review_result: dict
    ):
        """Post review results to GitHub."""
        try:
            # Determine review event
            recommendation = review_result.get("recommendation", "comment")

            github_event_map = {
                "approve": "APPROVE",
                "request_changes": "REQUEST_CHANGES",
                "comment": "COMMENT",
            }

            event = github_event_map.get(recommendation, "COMMENT")

            # Format review summary
            summary = self._format_review_summary(review_result)

            # Prepare inline comments
            inline_comments = []
            for comment in review_result.get("comments", []):
                if comment.get("filename") and comment.get("line_number"):
                    inline_comments.append(
                        {
                            "path": comment["filename"],
                            "line": comment["line_number"],
                            "body": f"**{comment['severity'].upper()}**: {comment['message']}"
                            + (
                                f"\n\n💡 **Suggestion**: {comment['suggestion']}"
                                if comment.get("suggestion")
                                else ""
                            ),
                        }
                    )

            # Log the review text before posting
            self.logger.info(
                "Review text to be posted to GitHub",
                repo=repository,
                pr=pr_number,
                review_body=summary,
                inline_comments_count=len(inline_comments),
            )

            # Also log the full review text for debugging
            self.logger.debug(
                "Full review content",
                review_text=summary,
                findings=review_result.get("findings", []),
            )

            # Submit review
            github_client = self._get_client()
            await github_client.submit_review(
                repository=repository,
                pr_number=pr_number,
                event=event,
                body=summary,
                comments=inline_comments[:20],  # Limit to 20 inline comments
            )

            self.logger.info(
                "Review posted to GitHub",
                repo=repository,
                pr=pr_number,
                review_event=event,
                inline_comments=len(inline_comments),
            )

        except Exception as e:
            self.logger.error(
                "Failed to post review", repo=repository, pr=pr_number, error=str(e)
            )
            raise

    async def post_error_comment(
        self, repository: str, pr_number: int, error_message: str
    ):
        """Post error comment to PR."""
        try:
            github_client = self._get_client()
            await github_client.post_review_comment(
                repository,
                pr_number,
                f"❌ **Junior Review Failed**\n\nI encountered an error while reviewing this PR: {error_message}\n\nPlease check the service logs for more details.",
            )
        except Exception as comment_error:
            self.logger.error("Failed to post error comment", error=str(comment_error))

    def _format_review_summary(self, review_result: dict) -> str:
        """Format review results into a GitHub comment."""
        summary = review_result.get("summary", "Review completed")

        # Add findings summary
        total = review_result.get("total_findings", 0)
        critical = review_result.get("critical_count", 0)
        high = review_result.get("high_count", 0)
        medium = review_result.get("medium_count", 0)
        low = review_result.get("low_count", 0)

        if total == 0:
            findings_summary = "✅ No issues found! Great work!"
        else:
            findings_summary = f"📊 **Findings Summary**: {total} total"
            if critical > 0:
                findings_summary += f" • 🔴 {critical} critical"
            if high > 0:
                findings_summary += f" • 🟠 {high} high"
            if medium > 0:
                findings_summary += f" • 🟡 {medium} medium"
            if low > 0:
                findings_summary += f" • 🟢 {low} low"

        # Format detailed findings
        findings_details = ""
        findings = review_result.get("findings", [])
        if findings:
            findings_details = "\n\n## 📋 Detailed Findings\n"

            # Group findings by severity for better organization
            severity_groups = {
                "critical": [],
                "high": [],
                "medium": [],
                "low": []
            }

            for finding in findings:
                severity = finding.get("severity", "low")
                if severity in severity_groups:
                    severity_groups[severity].append(finding)

            # Format each severity group
            severity_emojis = {
                "critical": "🔴",
                "high": "🟠",
                "medium": "🟡",
                "low": "🟢"
            }

            for severity in ["critical", "high", "medium", "low"]:
                if severity_groups[severity]:
                    findings_details += f"\n### {severity_emojis[severity]} {severity.capitalize()} Issues\n"
                    for finding in severity_groups[severity]:
                        category = finding.get("category", "general").replace("_", " ").title()
                        message = finding.get("message", "")
                        file_path = finding.get("file_path", "")
                        line_num = finding.get("line_number", "")
                        suggestion = finding.get("suggestion", "")
                        principle = finding.get("principle_violated", "")

                        findings_details += f"\n**[{category}]** {message}"

                        if file_path:
                            location = f"`{file_path}`"
                            if line_num:
                                location += f" (line {line_num})"
                            findings_details += f"\n📍 Location: {location}"

                        if suggestion:
                            findings_details += f"\n💡 **Suggestion:** {suggestion}"

                        if principle:
                            findings_details += f"\n📐 **Principle:** {principle}"

                        findings_details += "\n"

        # Format final comment
        formatted_summary = f"""## 🤖 Junior Code Review

{summary}

{findings_summary}
{findings_details}
---
*Reviewed by Junior AI Agent - Focusing on logic, security, and code quality*
"""

        return formatted_summary

    async def get_authenticated_user(self):
        """Get authenticated user for health checks."""
        github_client = self._get_client()
        return await github_client.get_authenticated_user()
