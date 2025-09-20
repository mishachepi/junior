"""Tests for FastAPI webhook endpoints."""

import json
from unittest.mock import AsyncMock, MagicMock, patch
from dotenv import load_dotenv

load_dotenv()  # loads from .env

import pytest
from fastapi.testclient import TestClient

from junior.api import app
from junior.github_client import GitHubClient


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


# @pytest.fixture
# def sample_webhook_payload():
#     """Sample GitHub webhook payload."""
#     return {
#         "action": "opened",
#         "number": 123,
#         "pull_request": {
#             "id": 123,
#             "title": "Test PR",
#             "body": "Test description",
#             "state": "open",
#             "draft": False,
#             "user": {"login": "testuser", "id": 1},
#             "base": {"ref": "main", "sha": "abc123"},
#             "head": {"ref": "feature/test", "sha": "def456"},
#             "diff_url": "https://github.com/test/repo/pull/123.diff",
#             "patch_url": "https://github.com/test/repo/pull/123.patch",
#             "created_at": "2023-01-01T00:00:00Z",
#             "updated_at": "2023-01-01T00:00:00Z",
#             "additions": 50,
#             "deletions": 10,
#             "changed_files": 3,
#         },
#         "repository": {
#             "id": 456,
#             "full_name": "test/repo",
#             "clone_url": "https://github.com/test/repo.git",
#             "ssh_url": "git@github.com:test/repo.git",
#             "default_branch": "main",
#             "language": "Python",
#             "size": 1000,
#             "private": False,
#         },
#         "sender": {"login": "testuser", "id": 1}
#     }

@pytest.mark.integration
@pytest.mark.asyncio
async def test_post_review_comment_integration():
    """Test posting a review comment - debugger friendly version."""
    import os

    # Set breakpoint here in VSCode
    print("Starting test_post_review_comment_integration")

    # Use real GitHub API (remove mock for debugging)
    repository = "mishachepi/junior"
    pr_number = 1
    body = f"Debug test comment - {os.urandom(4).hex()}"

    # Create client - set breakpoint here to inspect token
    github_client = GitHubClient()

    # Fetch PR info first - set breakpoint to see PR details
    pr_info = await github_client.get_pull_request(repository, pr_number)
    print(f"PR state: {pr_info.get('state')}")

    # Post comment - set breakpoint to debug the actual API call
    response = await github_client.post_review_comment(
        repository=repository,
        pr_number=pr_number,
        body=body,
    )

    # Check response - set breakpoint to inspect response
    assert response is not None
    assert response.get("body") == body
    print(f"Test passed! Comment ID: {response.get('id')}")


# @pytest.mark.integration
@pytest.mark.asyncio
async def test_post_review_comment_real_debug():
    """Debug version - Test posting a review comment with REAL GitHub API."""
    import os
    import traceback

    # Print debug info
    print("\n=== DEBUG: Starting real GitHub API test ===")

    # Check token
    token = os.getenv("GITHUB_TOKEN")
    print(f"Token exists: {bool(token)}")
    print(f"Token prefix: {token[:10]}..." if token else "No token")

    try:
        # Use a real public test repository - you can change this to your own test repo
        repository = "mishachepi/junior"  # Change to your test repo
        pr_number = 1  # Change to an actual open PR number in your test repo
        body = f"Integration test comment from Junior - {os.urandom(4).hex()}"

        print(f"\nTrying to post to: {repository} PR #{pr_number}")
        print(f"Comment body: {body}")

        github_client = GitHubClient()
        print("GitHub client created successfully")

        # First, let's try to get the PR info to verify access
        print("\nFetching PR info first...")
        pr_info = await github_client.get_pull_request(repository, pr_number)
        print(f"PR title: {pr_info.get('title')}")
        print(f"PR state: {pr_info.get('state')}")
        print(f"PR author: {pr_info.get('user', {}).get('login')}")

        # Now try to post the comment
        print("\nPosting comment...")
        response = await github_client.post_review_comment(
            repository=repository,
            pr_number=pr_number,
            body=body,
        )

        print(f"\nSuccess! Response:")
        print(f"  Comment ID: {response.get('id')}")
        print(f"  Comment body: {response.get('body')}")
        print(f"  Created at: {response.get('created_at')}")

        assert response is not None
        assert response.get("body") == body
        print("\n=== All assertions passed! ===")

    except Exception as e:
        print(f"\n!!! ERROR: {type(e).__name__}: {str(e)}")
        print("\nFull traceback:")
        traceback.print_exc()
        raise


class TestUtilityFunctions:
    """Tests for utility functions."""
    
    def test_format_review_summary_no_issues(self):
        """Test formatting review summary with no issues."""
        from junior.api import format_review_summary
        
        review_result = {
            "summary": "Great code!",
            "total_findings": 0,
            "critical_count": 0,
            "high_count": 0,
            "medium_count": 0,
            "low_count": 0
        }
        
        formatted = format_review_summary(review_result)
        
        assert "Great code!" in formatted
        assert "✅ No issues found!" in formatted
        assert "Junior Code Review" in formatted
    
    def test_format_review_summary_with_issues(self):
        """Test formatting review summary with issues."""
        from junior.api import format_review_summary
        
        review_result = {
            "summary": "Several issues found",
            "total_findings": 5,
            "critical_count": 1,
            "high_count": 2,
            "medium_count": 1,
            "low_count": 1
        }
        
        formatted = format_review_summary(review_result)
        
        assert "Several issues found" in formatted
        assert "📊 **Findings Summary**: 5 total" in formatted
        assert "🔴 1 critical" in formatted
        assert "🟠 2 high" in formatted
        assert "🟡 1 medium" in formatted
        assert "🟢 1 low" in formatted