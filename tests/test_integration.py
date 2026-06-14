"""Integration tests: full runbook collect → review → publish with mocked AI."""

import pytest

from junior.config import (
    HarnessKind,
    ContextSettings,
    OutputSettings,
    LLMSettings,
    Settings,
)
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


class TestModuleContracts:
    """Each platform/engine module exports the function its caller expects."""

    def test_collectors_export_collect(self):
        import importlib

        for path in (
            "junior.collect.local",
            "junior.collect.gitlab",
            "junior.collect.github",
            "junior.collect.bitbucket",
        ):
            assert hasattr(importlib.import_module(path), "collect"), f"{path} missing collect()"

    def test_publishers_export_post_review(self):
        import importlib

        for path in (
            "junior.publish.local",
            "junior.publish.gitlab",
            "junior.publish.github",
            "junior.publish.bitbucket",
        ):
            assert hasattr(importlib.import_module(path), "post_review"), f"{path} missing post_review()"

    def test_engines_export_engine(self):
        """Engines may have optional deps — test what's installed."""
        import importlib

        for backend in HarnessKind:
            try:
                module = importlib.import_module(backend.value)
                assert hasattr(module, "HARNESS"), f"{backend.name} missing HARNESS"
            except ImportError:
                pytest.skip(f"{backend.name} has uninstalled optional dependencies")

    def test_agent_short_name_resolution(self):
        assert HarnessKind("pydantic") == HarnessKind.PYDANTIC
        assert HarnessKind("codex") == HarnessKind.CODEX


class TestFullRunbook:
    """Test the full collect → review → publish runbook with mocks."""

    def test_local_collect_to_local_publish(self, sample_context, sample_review_result, tmp_path):
        """Full runbook: local collect → mocked AI → local publish (file)."""
        output_file = tmp_path / "review.md"

        settings = Settings(
            context=ContextSettings(project_dir=str(tmp_path)),
            output=OutputSettings(output_file=str(output_file)),
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

        settings = Settings(llm=LLMSettings(harness=HarnessKind.PYDANTIC))
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
        from junior.runbooks.code_review.render import build_user_message

        msg = build_user_message(sample_context)

        assert "feat: add greeting" in msg
        assert "Adds a hello function" in msg
        assert "feature/hello" in msg
        assert "Add hello function" in msg
        assert "hello.py" in msg
        assert "def hello(): pass" in msg

    def test_render_inlines_small_diff_even_with_file_access(self, sample_context):
        """A small diff is the review's primary evidence — file-access engines
        get it inlined too, so a regression visible only in removed lines
        isn't misread as pre-existing code."""
        from junior.runbooks.code_review.local import LocalReview

        msg = LocalReview().render(sample_context, Settings(), file_access=True)

        assert "### Diff" in msg
        assert sample_context.full_diff in msg

    def test_render_oversized_diff_falls_back_to_file_tools(self, sample_context):
        from junior.runbooks.code_review.base import INLINE_DIFF_MAX_CHARS
        from junior.runbooks.code_review.local import LocalReview

        big = sample_context.model_copy(
            update={"full_diff": "+x\n" * (INLINE_DIFF_MAX_CHARS // 2)}
        )
        msg = LocalReview().render(big, Settings(), file_access=True)

        assert "### Diff" not in msg
        assert "file reading tools" in msg
        # SDK engines (no file access) still get even a big diff inlined.
        sdk_msg = LocalReview().render(big, Settings(), file_access=False)
        assert "### Diff" in sdk_msg


class TestPreflight:
    """Generic (runbook-agnostic) validation. Publish checks live in runbooks."""

    def test_no_review_skips_review_validation(self):
        settings = Settings()
        errors = settings.preflight(review=False)
        assert errors == []

    def test_review_without_key_fails(self):
        settings = Settings(llm=LLMSettings(harness=HarnessKind.PYDANTIC))
        errors = settings.preflight(review=True)
        assert any("MODEL provider" in e or "API_KEY" in e for e in errors)
