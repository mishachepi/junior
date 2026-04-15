"""Integration tests: full pipeline collect → review → publish with mocked AI."""

from unittest.mock import patch

import pytest

from junior.config import AgentBackend, CollectorBackend, PublishBackend, Settings
from junior.models import (
    ChangedFile,
    CollectedContext,
    FileStatus,
    Recommendation,
    ReviewComment,
    ReviewCategory,
    ReviewResult,
    Severity,
)


# --- Fixtures ---


@pytest.fixture
def sample_context():
    """Minimal CollectedContext for integration testing."""
    return CollectedContext(
        mr_title="feat: add greeting",
        mr_description="Adds a hello function",
        source_branch="feature/hello",
        target_branch="main",
        commit_messages=["Add hello function"],
        full_diff="diff --git a/hello.py b/hello.py\n+def hello(): pass\n",
        changed_files=[
            ChangedFile(
                path="hello.py",
                status=FileStatus.ADDED,
                diff="+def hello(): pass\n",
                content="def hello(): pass\n",
            ),
        ],
    )


@pytest.fixture
def sample_review_result():
    """Minimal ReviewResult from a mocked AI agent."""
    return ReviewResult(
        summary="Code looks clean with one minor issue.",
        recommendation=Recommendation.COMMENT,
        comments=[
            ReviewComment(
                category=ReviewCategory.LOGIC,
                severity=Severity.LOW,
                message="Consider adding a docstring",
                file_path="hello.py",
                line_number=1,
                suggestion="Add a docstring to the function.",
            ),
        ],
        tokens_used=3000,
    )


# --- Tests ---


class TestEnumDispatch:
    """Test that all enum-based dispatches resolve to importable modules."""

    def test_all_collector_backends_importable(self):
        import importlib

        for backend in CollectorBackend:
            module = importlib.import_module(backend.value)
            assert hasattr(module, "collect"), f"{backend.name} missing collect()"

    def test_all_agent_backends_importable(self):
        """Agent backends may have optional deps — test what we can."""
        import importlib

        for backend in AgentBackend:
            try:
                module = importlib.import_module(backend.value)
                assert hasattr(module, "review"), f"{backend.name} missing review()"
            except ImportError:
                pytest.skip(f"{backend.name} has uninstalled optional dependencies")

    def test_all_publish_backends_importable(self):
        import importlib

        for backend in PublishBackend:
            module = importlib.import_module(backend.value)
            assert hasattr(module, "post_review"), f"{backend.name} missing post_review()"

    def test_short_name_resolution(self):
        assert AgentBackend("pydantic") == AgentBackend.PYDANTIC
        assert CollectorBackend("github") == CollectorBackend.GITHUB
        assert PublishBackend("local") == PublishBackend.LOCAL


class TestAutoDetection:
    """Test platform auto-detection via tokens."""

    def test_no_tokens_defaults_to_local(self):
        settings = Settings(gitlab_token="", github_token="")
        assert settings.resolved_collector == CollectorBackend.LOCAL
        assert settings.resolved_publisher == PublishBackend.LOCAL

    def test_gitlab_token_auto_detects(self):
        settings = Settings(gitlab_token="glpat-xxx", github_token="")
        assert settings.resolved_collector == CollectorBackend.GITLAB
        assert settings.resolved_publisher == PublishBackend.GITLAB

    def test_github_token_auto_detects(self):
        settings = Settings(gitlab_token="", github_token="ghp-xxx")
        assert settings.resolved_collector == CollectorBackend.GITHUB
        assert settings.resolved_publisher == PublishBackend.GITHUB


class TestFullPipeline:
    """Test the full collect → review → publish pipeline with mocks."""

    def test_local_collect_to_local_publish(self, sample_context, sample_review_result, tmp_path):
        """Full pipeline: local collect → mocked AI → local publish (file)."""
        output_file = tmp_path / "review.md"

        settings = Settings(
            ci_project_dir=str(tmp_path),
            publish_output=str(output_file),
        )

        from junior.publish.local import post_review

        post_review(settings, sample_review_result)

        assert output_file.exists()
        content = output_file.read_text()
        assert "Junior Code Review" in content
        assert "Consider adding a docstring" in content
        assert "claudecode" in content

    def test_formatter_produces_valid_output(self, sample_review_result):
        """Format review and check it contains all expected sections."""
        from junior.publish.core import format_summary

        settings = Settings(agent_backend=AgentBackend.PYDANTIC)
        output = format_summary(sample_review_result, settings=settings)

        assert "Junior Code Review" in output
        assert "Code looks clean" in output
        assert "Severity" in output
        assert "Low" in output
        assert "Consider adding a docstring" in output
        assert "hello.py:1" in output
        assert "pydantic" in output
        assert "3,000 tokens" in output

    def test_context_builder_includes_all_sections(self, sample_context):
        """Context builder should include all MR data for AI."""
        from junior.agent.core import build_user_message

        msg = build_user_message(sample_context)

        assert "feat: add greeting" in msg
        assert "Adds a hello function" in msg
        assert "feature/hello" in msg
        assert "Add hello function" in msg
        assert "hello.py" in msg
        assert "def hello(): pass" in msg


class TestPreflight:
    """Test configuration validation via preflight()."""

    def test_no_review_skips_review_validation(self):
        settings = Settings()
        errors = settings.preflight(review=False, publish=False)
        assert errors == []

    def test_publish_without_token_fails(self):
        settings = Settings(gitlab_token="", github_token="")
        errors = settings.preflight(review=False, publish=True)
        assert any("--publish" in e for e in errors)

    def test_gitlab_publish_requires_ids(self):
        settings = Settings(gitlab_token="glpat-xxx")
        errors = settings.preflight(review=False, publish=True)
        assert any("CI_PROJECT_ID" in e for e in errors)

    def test_gitlab_publish_valid(self):
        settings = Settings(
            gitlab_token="glpat-xxx",
            ci_project_id=123,
            ci_merge_request_iid=45,
        )
        errors = settings.preflight(review=False, publish=True)
        assert errors == []
