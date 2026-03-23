"""Tests for data models."""

from junior.models import (
    Recommendation,
    ReviewComment,
    ReviewCategory,
    ReviewResult,
    Severity,
)


def test_review_result_critical_count():
    result = ReviewResult(
        summary="test",
        comments=[
            ReviewComment(
                category=ReviewCategory.SECURITY, severity=Severity.CRITICAL, message="a"
            ),
            ReviewComment(category=ReviewCategory.LOGIC, severity=Severity.HIGH, message="b"),
            ReviewComment(category=ReviewCategory.LOGIC, severity=Severity.CRITICAL, message="c"),
        ],
    )
    assert result.critical_count == 2
    assert result.high_count == 1


def test_review_result_has_blocking_critical():
    result = ReviewResult(
        summary="test",
        comments=[
            ReviewComment(
                category=ReviewCategory.SECURITY, severity=Severity.CRITICAL, message="x"
            ),
        ],
    )
    assert result.has_blocking_issues is True


def test_review_result_has_blocking_request_changes():
    result = ReviewResult(
        summary="test",
        recommendation=Recommendation.REQUEST_CHANGES,
    )
    assert result.has_blocking_issues is True


def test_review_result_no_blocking():
    result = ReviewResult(
        summary="test",
        recommendation=Recommendation.APPROVE,
        comments=[
            ReviewComment(category=ReviewCategory.NAMING, severity=Severity.LOW, message="x"),
        ],
    )
    assert result.has_blocking_issues is False


def test_review_result_empty():
    result = ReviewResult(summary="all good")
    assert result.critical_count == 0
    assert result.high_count == 0
    assert result.has_blocking_issues is False
