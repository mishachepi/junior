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
        recommendation = review_result.get("recommendation", "comment")

        # Add findings summary
        total = review_result.get("total_findings", 0)
        critical = review_result.get("critical_count", 0)
        high = review_result.get("high_count", 0)
        medium = review_result.get("medium_count", 0)
        low = review_result.get("low_count", 0)

        # Create enhanced findings breakdown
        if total == 0:
            findings_section = ""  # No need for findings section if no issues
            action_section = "\n🎯 **Next Steps**: This PR is ready for merge! No issues found during logic, security, and architecture review."
        else:
            # Findings breakdown
            findings_parts = []
            if critical > 0:
                findings_parts.append(f"🔴 **{critical} Critical** - Requires immediate attention")
            if high > 0:
                findings_parts.append(f"🟠 **{high} High** - Should be addressed before merge")
            if medium > 0:
                findings_parts.append(f"🟡 **{medium} Medium** - Recommended improvements")
            if low > 0:
                findings_parts.append(f"🟢 **{low} Low** - Minor suggestions")
            
            findings_section = f"\n📊 **Issues Found**: {total} total\n" + "\n".join([f"- {part}" for part in findings_parts])
            
            # Action recommendations
            if recommendation == "request_changes":
                action_section = "\n🚨 **Action Required**: Please address the critical/high-priority issues above before merging."
            elif recommendation == "comment":
                action_section = "\n💡 **Suggestions**: Consider reviewing the issues above to improve code quality."
            else:
                action_section = "\n✅ **Ready to Merge**: Minor issues found but nothing blocking."

        # Format final comment with better structure
        formatted_summary = f"""## 🤖 Junior Code Review

{summary}{findings_section}{action_section}

---
*🔍 Analyzed for logic flaws, security vulnerabilities, and critical bugs • [Learn more about Junior](https://github.com/your-org/junior)*
"""

        return formatted_summary

    async def get_authenticated_user(self):
        """Get authenticated user for health checks."""
        github_client = self._get_client()
        return await github_client.get_authenticated_user()
