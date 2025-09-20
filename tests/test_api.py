"""Tests for FastAPI webhook endpoints."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from junior.api import app


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def sample_webhook_payload():
    """Sample GitHub webhook payload."""
    return {
        "action": "opened",
        "number": 123,
        "pull_request": {
            "id": 123,
            "title": "Test PR",
            "body": "Test description",
            "state": "open",
            "draft": False,
            "user": {"login": "testuser", "id": 1},
            "base": {"ref": "main", "sha": "abc123"},
            "head": {"ref": "feature/test", "sha": "def456"},
            "diff_url": "https://github.com/test/repo/pull/123.diff",
            "patch_url": "https://github.com/test/repo/pull/123.patch",
            "created_at": "2023-01-01T00:00:00Z",
            "updated_at": "2023-01-01T00:00:00Z",
            "additions": 50,
            "deletions": 10,
            "changed_files": 3,
        },
        "repository": {
            "id": 456,
            "full_name": "test/repo",
            "clone_url": "https://github.com/test/repo.git",
            "ssh_url": "git@github.com:test/repo.git",
            "default_branch": "main",
            "language": "Python",
            "size": 1000,
            "private": False,
        },
        "sender": {"login": "testuser", "id": 1}
    }


class TestHealthEndpoints:
    """Tests for health check endpoints."""
    
    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "junior-webhook"
    
    @patch("junior.api.github_client.get_authenticated_user")
    def test_readiness_check_success(self, mock_get_user, client):
        """Test successful readiness check."""
        mock_get_user.return_value = {"login": "testuser"}
        
        response = client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
    
    @patch("junior.api.github_client.get_authenticated_user")
    def test_readiness_check_failure(self, mock_get_user, client):
        """Test failed readiness check."""
        mock_get_user.side_effect = Exception("GitHub API error")
        
        response = client.get("/ready")
        assert response.status_code == 503
        data = response.json()
        assert "not ready" in data["detail"]


class TestWebhookEndpoint:
    """Tests for GitHub webhook endpoint."""
    
    @patch("junior.api.webhook_processor.verify_signature")
    @patch("junior.api.webhook_processor.should_process_event")
    @patch("junior.api.webhook_processor.extract_review_data")
    def test_webhook_success(
        self, 
        mock_extract_data,
        mock_should_process,
        mock_verify_sig,
        client, 
        sample_webhook_payload
    ):
        """Test successful webhook processing."""
        # Setup mocks
        mock_verify_sig.return_value = True
        mock_should_process.return_value = True
        mock_extract_data.return_value = {
            "repository": "test/repo",
            "pr_number": 123,
            "title": "Test PR"
        }
        
        response = client.post(
            "/webhook/github",
            json=sample_webhook_payload,
            headers={"X-Hub-Signature-256": "sha256=valid_signature"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "PR review queued"
        assert data["repository"] == "test/repo"
        assert data["pr_number"] == 123
        assert data["action"] == "opened"
    
    @patch("junior.api.webhook_processor.verify_signature")
    def test_webhook_invalid_signature(self, mock_verify_sig, client, sample_webhook_payload):
        """Test webhook with invalid signature."""
        mock_verify_sig.return_value = False
        
        response = client.post(
            "/webhook/github",
            json=sample_webhook_payload,
            headers={"X-Hub-Signature-256": "sha256=invalid_signature"}
        )
        
        assert response.status_code == 401
        data = response.json()
        assert "Invalid webhook signature" in data["detail"]
    
    def test_webhook_invalid_json(self, client):
        """Test webhook with invalid JSON."""
        response = client.post(
            "/webhook/github",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "Invalid JSON payload" in data["detail"]
    
    @patch("junior.api.webhook_processor.verify_signature")
    def test_webhook_not_pr_event(self, mock_verify_sig, client):
        """Test webhook that's not a pull request event."""
        mock_verify_sig.return_value = True
        
        non_pr_payload = {
            "action": "created",
            "issue": {"number": 123},
            "repository": {"full_name": "test/repo"}
        }
        
        response = client.post(
            "/webhook/github",
            json=non_pr_payload,
            headers={"X-Hub-Signature-256": "sha256=valid_signature"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "Not a pull request event" in data["message"]
    
    @patch("junior.api.webhook_processor.verify_signature")
    @patch("junior.api.webhook_processor.should_process_event")
    def test_webhook_skipped_action(
        self, 
        mock_should_process,
        mock_verify_sig,
        client, 
        sample_webhook_payload
    ):
        """Test webhook with skipped action."""
        mock_verify_sig.return_value = True
        mock_should_process.return_value = False
        
        sample_webhook_payload["action"] = "closed"
        
        response = client.post(
            "/webhook/github",
            json=sample_webhook_payload,
            headers={"X-Hub-Signature-256": "sha256=valid_signature"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "Skipping action: closed" in data["message"]


class TestManualReviewEndpoint:
    """Tests for manual review endpoint."""
    
    def test_manual_review_production_disabled(self, client, monkeypatch):
        """Test manual review disabled in production."""
        from junior.config import Settings
        prod_settings = Settings(
            github_token="test-token",
            secret_key="test-secret",
            debug=False  # Production mode
        )
        monkeypatch.setattr("junior.api.settings", prod_settings)
        
        response = client.post("/review", json={"repository": "test/repo", "pr_number": 123})
        assert response.status_code == 404
    
    @patch("junior.api.review_agent.review_pull_request")
    @patch("junior.api.get_pr_diff")
    def test_manual_review_success(
        self, 
        mock_get_diff,
        mock_review,
        client,
        monkeypatch
    ):
        """Test successful manual review."""
        from junior.config import Settings
        debug_settings = Settings(
            github_token="test-token",
            secret_key="test-secret",
            debug=True  # Debug mode
        )
        monkeypatch.setattr("junior.api.settings", debug_settings)
        
        # Setup mocks
        mock_get_diff.return_value = "diff content"
        mock_review.return_value = {
            "repository": "test/repo",
            "pr_number": 123,
            "summary": "Review completed",
            "total_findings": 0
        }
        
        response = client.post("/review", json={
            "repository": "test/repo",
            "pr_number": 123,
            "diff_content": "test diff"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["repository"] == "test/repo"
        assert data["pr_number"] == 123
    
    @patch("junior.api.review_agent.review_pull_request")
    def test_manual_review_error(self, mock_review, client, monkeypatch):
        """Test manual review with error."""
        from junior.config import Settings
        debug_settings = Settings(
            github_token="test-token",
            secret_key="test-secret",
            debug=True
        )
        monkeypatch.setattr("junior.api.settings", debug_settings)
        
        mock_review.side_effect = Exception("Review failed")
        
        response = client.post("/review", json={
            "repository": "test/repo",
            "pr_number": 123,
            "diff_content": "test diff"
        })
        
        assert response.status_code == 500
        data = response.json()
        assert "Review failed" in data["detail"]


@pytest.mark.asyncio
class TestBackgroundProcessing:
    """Tests for background processing functions."""
    
    @patch("junior.api.get_pr_diff")
    @patch("junior.api.analyze_repository")
    @patch("junior.api.review_agent.review_pull_request")
    @patch("junior.api.post_review_to_github")
    async def test_process_pr_review_success(
        self,
        mock_post_review,
        mock_review,
        mock_analyze,
        mock_get_diff
    ):
        """Test successful PR review processing."""
        from junior.api import process_pr_review
        
        # Setup mocks
        mock_get_diff.return_value = "diff content"
        mock_analyze.return_value = ({}, {})
        mock_review.return_value = {
            "repository": "test/repo",
            "pr_number": 123,
            "summary": "Review completed",
            "total_findings": 0,
            "recommendation": "approve"
        }
        mock_post_review.return_value = None
        
        review_data = {
            "repository": "test/repo",
            "pr_number": 123,
            "head_sha": "def456",
            "base_sha": "abc123"
        }
        
        # Should not raise exception
        await process_pr_review(review_data)
        
        mock_get_diff.assert_called_once()
        mock_analyze.assert_called_once()
        mock_review.assert_called_once()
        mock_post_review.assert_called_once()
    
    @patch("junior.api.get_pr_diff")
    @patch("junior.api.github_client.post_review_comment")
    async def test_process_pr_review_error_handling(
        self,
        mock_post_comment,
        mock_get_diff
    ):
        """Test PR review error handling."""
        from junior.api import process_pr_review
        
        # Setup mocks to fail
        mock_get_diff.side_effect = Exception("Failed to get diff")
        mock_post_comment.return_value = None
        
        review_data = {
            "repository": "test/repo",
            "pr_number": 123,
            "head_sha": "def456",
            "base_sha": "abc123"
        }
        
        # Should not raise exception (error is handled)
        await process_pr_review(review_data)
        
        # Should post error comment
        mock_post_comment.assert_called_once()
        call_args = mock_post_comment.call_args[0]
        assert "test/repo" in call_args
        assert 123 in call_args
        assert "Junior Review Failed" in call_args[2]


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