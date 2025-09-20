"""Webhook handler for GitHub PR events."""

import hashlib
import hmac

import structlog
from fastapi import Request
from pydantic import BaseModel, Field

from ..config import settings

logger = structlog.get_logger(__name__)


class PullRequestWebhookPayload(BaseModel):
    """GitHub pull request webhook payload."""

    action: str = Field(..., description="The action that was performed")
    number: int = Field(..., description="Pull request number")
    pull_request: dict = Field(..., description="Pull request data")
    repository: dict = Field(..., description="Repository data")
    sender: dict = Field(..., description="User who triggered the event")
    label: dict | None = Field(None, description="Label data for labeled action")


class WebhookProcessor:
    """Process GitHub webhook events."""

    def __init__(self):
        self.logger = logger.bind(component="WebhookProcessor")

    async def verify_signature(self, request: Request, payload: bytes) -> bool:
        """Verify GitHub webhook signature."""
        if not settings.github_webhook_secret:
            self.logger.warning("No webhook secret configured, skipping verification")
            return True

        signature_header = request.headers.get("X-Hub-Signature-256")
        if not signature_header:
            self.logger.error("No signature header found")
            return False

        try:
            # GitHub sends signature as 'sha256=<hash>'
            expected_signature = signature_header.split("=")[1]

            # Calculate HMAC
            mac = hmac.new(
                settings.github_webhook_secret.encode("utf-8"), payload, hashlib.sha256
            )
            calculated_signature = mac.hexdigest()

            # Secure comparison
            is_valid = hmac.compare_digest(expected_signature, calculated_signature)

            if not is_valid:
                self.logger.error("Invalid webhook signature")

            return is_valid

        except Exception as e:
            self.logger.error("Error verifying signature", error=str(e))
            return False

    def should_process_event(self, payload: PullRequestWebhookPayload) -> bool:
        """Determine if we should process this PR event."""
        # Process these actions
        valid_actions = {
            "opened",
            "synchronize",  # New commits pushed
            "reopened",
            "ready_for_review",  # When draft is marked ready
            "labeled",  # When a label is added
        }

        if payload.action not in valid_actions:
            self.logger.info("Skipping action", action=payload.action)
            return False

        # Skip draft PRs (unless ready_for_review)
        if (
            payload.pull_request.get("draft", False)
            and payload.action != "ready_for_review"
        ):
            self.logger.info("Skipping draft PR", pr_number=payload.number)
            return False

        # Skip if PR is already merged or closed
        if payload.pull_request.get("state") != "open":
            self.logger.info(
                "Skipping non-open PR",
                pr_number=payload.number,
                state=payload.pull_request.get("state"),
            )
            return False

        return True

    def extract_minimal_review_data(self, payload: PullRequestWebhookPayload) -> dict:
        """Extract minimal data required for code review with on-demand fetching."""
        pr = payload.pull_request
        repo = payload.repository

        # Return only essential data - everything else can be fetched via MCP
        return {
            "repository": repo["full_name"],
            "pr_number": payload.number,
            "title": pr["title"],
            "description": pr.get("body", ""),
            "author": pr["user"]["login"],
            "base_branch": pr["base"]["ref"],
            "head_branch": pr["head"]["ref"],
            "base_sha": pr["base"]["sha"],
            "head_sha": pr["head"]["sha"],
            "diff_url": pr.get("diff_url", ""),
            "clone_url": repo.get("clone_url", ""),
        }

    def extract_review_data(self, payload: PullRequestWebhookPayload) -> dict:
        """Extract comprehensive data for code review - kept for backward compatibility."""
        return self.extract_minimal_review_data(payload)

    def _extract_linked_issues(self, pr_body: str) -> list[dict]:
        """Extract linked issues from PR description."""
        import re

        if not pr_body:
            return []

        # Common patterns for linking issues
        patterns = [
            r"(?:close|closes|closed|fix|fixes|fixed|resolve|resolves|resolved)\s+#(\d+)",
            r"(?:close|closes|closed|fix|fixes|fixed|resolve|resolves|resolved)\s+(?:https://github\.com/[^/]+/[^/]+/issues/)(\d+)",
            r"#(\d+)",  # Simple issue references
        ]

        linked_issues = []
        for pattern in patterns:
            matches = re.finditer(pattern, pr_body, re.IGNORECASE)
            for match in matches:
                issue_number = int(match.group(1))
                if issue_number not in [issue["number"] for issue in linked_issues]:
                    linked_issues.append(
                        {
                            "number": issue_number,
                            "type": "closes"
                            if "close" in match.group(0).lower()
                            or "fix" in match.group(0).lower()
                            or "resolve" in match.group(0).lower()
                            else "references",
                        }
                    )

        return linked_issues
