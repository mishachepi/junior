"""Tests for webhook functionality."""

import hashlib
import hmac
from unittest.mock import MagicMock

import pytest

from junior.services import PullRequestWebhookPayload, WebhookProcessor


class TestWebhookProcessor:
    """Tests for WebhookProcessor."""

    def test_webhook_payload_validation(self):
        """Test webhook payload validation."""
        valid_payload = {
            "action": "opened",
            "number": 123,
            "pull_request": {
                "id": 123,
                "title": "Test PR",
                "body": "Test description",
                "state": "open",
                "draft": False,
                "user": {"login": "testuser"},
                "base": {"ref": "main", "sha": "abc123"},
                "head": {"ref": "feature", "sha": "def456"},
                "diff_url": "https://github.com/test/repo/pull/123.diff",
                "patch_url": "https://github.com/test/repo/pull/123.patch",
                "created_at": "2023-01-01T00:00:00Z",
                "updated_at": "2023-01-01T00:00:00Z",
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
            "sender": {"login": "testuser", "id": 789}
        }

        payload = PullRequestWebhookPayload(**valid_payload)
        assert payload.action == "opened"
        assert payload.number == 123
        assert payload.pull_request["title"] == "Test PR"

    @pytest.mark.asyncio
    async def test_verify_signature_valid(self):
        """Test valid signature verification."""
        processor = WebhookProcessor()

        # Mock settings
        from junior.config import Settings
        test_settings = Settings(
            github_token="test-token",
            secret_key="test-secret",
            github_webhook_secret="test-webhook-secret"
        )

        with pytest.MonkeyPatch().context() as m:
            m.setattr("junior.webhook.settings", test_settings)

            payload = b'{"test": "data"}'
            expected_signature = hmac.new(
                b"test-webhook-secret",
                payload,
                hashlib.sha256
            ).hexdigest()

            # Mock request
            request = MagicMock()
            request.headers.get.return_value = f"sha256={expected_signature}"

            is_valid = await processor.verify_signature(request, payload)
            assert is_valid

    @pytest.mark.asyncio
    async def test_verify_signature_invalid(self):
        """Test invalid signature verification."""
        processor = WebhookProcessor()

        from junior.config import Settings
        test_settings = Settings(
            github_token="test-token",
            secret_key="test-secret",
            github_webhook_secret="test-webhook-secret"
        )

        with pytest.MonkeyPatch().context() as m:
            m.setattr("junior.webhook.settings", test_settings)

            payload = b'{"test": "data"}'

            # Mock request with wrong signature
            request = MagicMock()
            request.headers.get.return_value = "sha256=invalid_signature"

            is_valid = await processor.verify_signature(request, payload)
            assert not is_valid

    @pytest.mark.asyncio
    async def test_verify_signature_no_secret(self):
        """Test signature verification when no secret is configured."""
        processor = WebhookProcessor()

        from junior.config import Settings
        test_settings = Settings(
            github_token="test-token",
            secret_key="test-secret"
        )

        with pytest.MonkeyPatch().context() as m:
            m.setattr("junior.webhook.settings", test_settings)

            payload = b'{"test": "data"}'
            request = MagicMock()

            is_valid = await processor.verify_signature(request, payload)
            assert is_valid  # Should pass when no secret configured

    def test_should_process_event_valid_actions(self):
        """Test processing of valid actions."""
        processor = WebhookProcessor()

        valid_actions = ["opened", "synchronize", "reopened", "ready_for_review", "labeled"]

        for action in valid_actions:
            payload = PullRequestWebhookPayload(
                action=action,
                number=123,
                pull_request={
                    "state": "open",
                    "draft": False,
                    "title": "Test",
                    "user": {"login": "test"},
                    "base": {"ref": "main", "sha": "abc"},
                    "head": {"ref": "feature", "sha": "def"},
                },
                repository={"full_name": "test/repo"},
                sender={"login": "test"}
            )

            should_process = processor.should_process_event(payload)
            assert should_process, f"Should process action: {action}"

    def test_should_process_event_invalid_actions(self):
        """Test skipping of invalid actions."""
        processor = WebhookProcessor()

        invalid_actions = ["closed", "assigned", "edited"]

        for action in invalid_actions:
            payload = PullRequestWebhookPayload(
                action=action,
                number=123,
                pull_request={
                    "state": "open",
                    "draft": False,
                    "title": "Test",
                    "user": {"login": "test"},
                    "base": {"ref": "main", "sha": "abc"},
                    "head": {"ref": "feature", "sha": "def"},
                },
                repository={"full_name": "test/repo"},
                sender={"login": "test"}
            )

            should_process = processor.should_process_event(payload)
            assert not should_process, f"Should not process action: {action}"

    def test_should_process_event_draft_pr(self):
        """Test skipping of draft PRs."""
        processor = WebhookProcessor()

        payload = PullRequestWebhookPayload(
            action="opened",
            number=123,
            pull_request={
                "state": "open",
                "draft": True,  # Draft PR
                "title": "Test",
                "user": {"login": "test"},
                "base": {"ref": "main", "sha": "abc"},
                "head": {"ref": "feature", "sha": "def"},
            },
            repository={"full_name": "test/repo"},
            sender={"login": "test"}
        )

        should_process = processor.should_process_event(payload)
        assert not should_process

    def test_should_process_event_ready_for_review_draft(self):
        """Test processing of ready_for_review action even for draft PRs."""
        processor = WebhookProcessor()

        payload = PullRequestWebhookPayload(
            action="ready_for_review",
            number=123,
            pull_request={
                "state": "open",
                "draft": True,  # Draft PR but ready for review
                "title": "Test",
                "user": {"login": "test"},
                "base": {"ref": "main", "sha": "abc"},
                "head": {"ref": "feature", "sha": "def"},
            },
            repository={"full_name": "test/repo"},
            sender={"login": "test"}
        )

        should_process = processor.should_process_event(payload)
        assert should_process

    def test_should_process_event_closed_pr(self):
        """Test skipping of closed PRs."""
        processor = WebhookProcessor()

        payload = PullRequestWebhookPayload(
            action="synchronize",
            number=123,
            pull_request={
                "state": "closed",  # Closed PR
                "draft": False,
                "title": "Test",
                "user": {"login": "test"},
                "base": {"ref": "main", "sha": "abc"},
                "head": {"ref": "feature", "sha": "def"},
            },
            repository={"full_name": "test/repo"},
            sender={"login": "test"}
        )

        should_process = processor.should_process_event(payload)
        assert not should_process

    def test_extract_review_data(self):
        """Test extraction of review data from webhook payload."""
        processor = WebhookProcessor()

        payload = PullRequestWebhookPayload(
            action="opened",
            number=123,
            pull_request={
                "title": "Test PR",
                "body": "Test description",
                "state": "open",
                "draft": False,
                "user": {"login": "testuser"},
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
            repository={
                "full_name": "test/repo",
                "clone_url": "https://github.com/test/repo.git",
                "ssh_url": "git@github.com:test/repo.git",
                "default_branch": "main",
                "language": "Python",
                "size": 1000,
                "private": False,
            },
            sender={"login": "testuser"}
        )

        review_data = processor.extract_minimal_review_data(payload)

        # Test minimal review data structure
        assert review_data["repository"] == "test/repo"
        assert review_data["pr_number"] == 123
        assert review_data["title"] == "Test PR"
        assert review_data["description"] == "Test description"
        assert review_data["author"] == "testuser"
        assert review_data["base_branch"] == "main"
        assert review_data["head_branch"] == "feature/test"
        assert review_data["base_sha"] == "abc123"
        assert review_data["head_sha"] == "def456"
        assert review_data["diff_url"] == "https://github.com/test/repo/pull/123.diff"
        assert review_data["clone_url"] == "https://github.com/test/repo.git"

        # These fields are no longer in minimal data (will be fetched on demand)
        assert "language" not in review_data
        assert "additions" not in review_data
        assert "deletions" not in review_data
        assert "changed_files" not in review_data
