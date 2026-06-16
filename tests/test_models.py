"""Tests for the code-review domain models."""

import pytest
from pydantic import ValidationError

from junior.runbook.base import Usage
from junior.runbooks.code_review.models import (
    Recommendation,
    ReviewCategory,
    ReviewComment,
    ReviewContext,
    ReviewOutput,
    ReviewResult,
    Severity,
    assemble_review_result,
)


# --- ReviewOutput counting / blocking logic ---


def test_review_output_critical_count():
    output = ReviewOutput(
        summary="test",
        comments=[
            ReviewComment(
                category=ReviewCategory.SECURITY, severity=Severity.CRITICAL, message="a"
            ),
            ReviewComment(category=ReviewCategory.LOGIC, severity=Severity.HIGH, message="b"),
            ReviewComment(category=ReviewCategory.LOGIC, severity=Severity.CRITICAL, message="c"),
        ],
    )
    assert output.critical_count == 2
    assert output.high_count == 1


def test_review_output_has_blocking_critical():
    output = ReviewOutput(
        summary="test",
        comments=[
            ReviewComment(
                category=ReviewCategory.SECURITY, severity=Severity.CRITICAL, message="x"
            ),
        ],
    )
    assert output.has_blocking_issues is True


def test_review_output_has_blocking_request_changes():
    output = ReviewOutput(summary="test", recommendation=Recommendation.REQUEST_CHANGES)
    assert output.has_blocking_issues is True


def test_review_output_no_blocking():
    output = ReviewOutput(
        summary="test",
        recommendation=Recommendation.APPROVE,
        comments=[
            ReviewComment(category=ReviewCategory.NAMING, severity=Severity.LOW, message="x"),
        ],
    )
    assert output.has_blocking_issues is False


def test_review_output_empty():
    output = ReviewOutput(summary="all good")
    assert output.critical_count == 0
    assert output.high_count == 0
    assert output.has_blocking_issues is False


# --- assemble_review_result: compose output + runtime metadata ---


def test_assemble_review_result_wraps_output_and_metadata():
    output = ReviewOutput(
        summary="Needs changes",
        recommendation=Recommendation.REQUEST_CHANGES,
        comments=[ReviewComment(category=ReviewCategory.BUG, severity=Severity.HIGH, message="Bug")],
    )
    usage = Usage(input_tokens=30, output_tokens=12, total_tokens=42)

    result = assemble_review_result(output, usage=usage, errors=["partial failure"])

    assert isinstance(result, ReviewResult)
    # The output instance is reused, not flattened/copied.
    assert result.output is output
    assert result.output.summary == "Needs changes"
    assert result.output.recommendation == Recommendation.REQUEST_CHANGES
    assert result.output.comments == output.comments
    assert result.usage.total_tokens == 42
    assert result.usage.input_tokens == 30
    assert result.usage.output_tokens == 12
    assert result.errors == ["partial failure"]


def test_assemble_review_result_defaults_errors_empty():
    result = assemble_review_result(ReviewOutput(summary="ok"), usage=Usage())
    assert result.errors == []


def test_review_result_is_llm_result_subclass():
    from junior.runbook.base import LLMResult

    assert issubclass(ReviewResult, LLMResult)


# --- ReviewComment normalisation (mode="before") ---


def test_review_comment_drops_orphan_line_number():
    comment = ReviewComment(
        category=ReviewCategory.LOGIC, severity=Severity.LOW, message="x", line_number=5
    )
    assert comment.line_number is None


def test_review_comment_keeps_line_with_file():
    comment = ReviewComment(
        category=ReviewCategory.LOGIC,
        severity=Severity.LOW,
        message="x",
        file_path="a.py",
        line_number=5,
    )
    assert comment.line_number == 5


# --- frozen: every domain model rejects mutation ---


def test_review_output_is_frozen():
    output = ReviewOutput(summary="x")
    with pytest.raises(ValidationError):
        output.summary = "y"


def test_review_comment_is_frozen():
    comment = ReviewComment(category=ReviewCategory.BUG, severity=Severity.LOW, message="m")
    with pytest.raises(ValidationError):
        comment.message = "n"


def test_review_context_is_frozen():
    context = ReviewContext(mr_title="t")
    with pytest.raises(ValidationError):
        context.mr_title = "z"


def test_review_result_is_frozen():
    result = ReviewResult(output=ReviewOutput(summary="x"))
    with pytest.raises(ValidationError):
        result.pre_formatted = "boom"


# --- deprecated shim aliases keep importing ---


def test_shim_aliases_resolve_to_renamed_models():
    from junior.models import CollectedContext, LLMReviewOutput

    assert CollectedContext is ReviewContext
    assert LLMReviewOutput is ReviewOutput
