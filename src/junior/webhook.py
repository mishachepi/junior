"""Webhook handler for GitHub PR events."""

import hashlib
import hmac
from typing import Dict, List, Optional

import structlog
from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from .config import settings

logger = structlog.get_logger(__name__)


class PullRequestWebhookPayload(BaseModel):
    """GitHub pull request webhook payload."""
    
    action: str = Field(..., description="The action that was performed")
    number: int = Field(..., description="Pull request number")
    pull_request: Dict = Field(..., description="Pull request data")
    repository: Dict = Field(..., description="Repository data")
    sender: Dict = Field(..., description="User who triggered the event")


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
                settings.github_webhook_secret.encode("utf-8"),
                payload,
                hashlib.sha256
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
            "ready_for_review"  # When draft is marked ready
        }
        
        if payload.action not in valid_actions:
            self.logger.info("Skipping action", action=payload.action)
            return False
        
        # Skip draft PRs (unless ready_for_review)
        if payload.pull_request.get("draft", False) and payload.action != "ready_for_review":
            self.logger.info("Skipping draft PR", pr_number=payload.number)
            return False
        
        # Skip if PR is already merged or closed
        if payload.pull_request.get("state") != "open":
            self.logger.info("Skipping non-open PR", 
                           pr_number=payload.number, 
                           state=payload.pull_request.get("state"))
            return False
        
        return True
    
    def extract_review_data(self, payload: PullRequestWebhookPayload) -> Dict:
        """Extract comprehensive data for code review."""
        pr = payload.pull_request
        repo = payload.repository
        
        # Extract commits information
        commits = []
        if "commits" in pr:
            for commit in pr["commits"]:
                commits.append({
                    "sha": commit["sha"],
                    "message": commit["commit"]["message"],
                    "author": commit["commit"]["author"]["name"],
                    "author_email": commit["commit"]["author"]["email"],
                    "date": commit["commit"]["author"]["date"],
                    "url": commit["html_url"]
                })
        
        # Extract linked issues from PR body
        linked_issues = self._extract_linked_issues(pr.get("body", ""))
        
        # Extract labels
        labels = []
        if "labels" in pr:
            labels = [label["name"] for label in pr["labels"]]
        
        # Extract requested reviewers
        requested_reviewers = []
        if "requested_reviewers" in pr:
            requested_reviewers = [reviewer["login"] for reviewer in pr["requested_reviewers"]]
        
        # Extract milestone
        milestone = None
        if pr.get("milestone"):
            milestone = {
                "title": pr["milestone"]["title"],
                "description": pr["milestone"]["description"],
                "due_on": pr["milestone"]["due_on"],
                "state": pr["milestone"]["state"]
            }
        
        return {
            # Basic PR info
            "repository": repo["full_name"],
            "pr_number": payload.number,
            "title": pr["title"],
            "description": pr.get("body", ""),
            "author": pr["user"]["login"],
            "author_id": pr["user"]["id"],
            
            # Branch and SHA info
            "base_branch": pr["base"]["ref"],
            "head_branch": pr["head"]["ref"],
            "base_sha": pr["base"]["sha"],
            "head_sha": pr["head"]["sha"],
            
            # URLs for data fetching
            "diff_url": pr["diff_url"],
            "patch_url": pr["patch_url"],
            "pr_url": pr["html_url"],
            "issue_url": pr["issue_url"],
            
            # Repository info
            "clone_url": repo["clone_url"],
            "ssh_url": repo["ssh_url"],
            "default_branch": repo["default_branch"],
            "language": repo.get("language"),
            "size": repo.get("size", 0),
            "is_private": repo.get("private", False),
            "repo_description": repo.get("description", ""),
            
            # Timing info
            "created_at": pr["created_at"],
            "updated_at": pr["updated_at"],
            "closed_at": pr.get("closed_at"),
            "merged_at": pr.get("merged_at"),
            
            # Change statistics
            "additions": pr.get("additions", 0),
            "deletions": pr.get("deletions", 0),
            "changed_files": pr.get("changed_files", 0),
            
            # PR state and metadata
            "state": pr["state"],
            "draft": pr.get("draft", False),
            "mergeable": pr.get("mergeable"),
            "mergeable_state": pr.get("mergeable_state"),
            "merged": pr.get("merged", False),
            "merge_commit_sha": pr.get("merge_commit_sha"),
            
            # Commits information
            "commits": commits,
            "commits_count": len(commits),
            
            # Related issues and PRs
            "linked_issues": linked_issues,
            "milestone": milestone,
            
            # Review metadata
            "labels": labels,
            "requested_reviewers": requested_reviewers,
            "assignees": [assignee["login"] for assignee in pr.get("assignees", [])],
            
            # GitHub event context
            "action": payload.action,
            "sender": payload.sender["login"],
            "webhook_received_at": None  # Will be set by the webhook handler
        }
    
    def _extract_linked_issues(self, pr_body: str) -> List[Dict]:
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
                    linked_issues.append({
                        "number": issue_number,
                        "type": "closes" if "close" in match.group(0).lower() or "fix" in match.group(0).lower() or "resolve" in match.group(0).lower() else "references"
                    })
        
        return linked_issues