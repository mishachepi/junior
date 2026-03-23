"""Tests for formatter: summary and inline comment formatting."""

from junior.publish.core import format_inline_comment, format_summary
from junior.models import (
    ReviewCategory,
    ReviewComment,
    ReviewResult,
    Severity,
)


def _make_comment(**kwargs):
    defaults = dict(
        category=ReviewCategory.LOGIC,
        severity=Severity.HIGH,
        message="Test issue",
        file_path="foo.py",
        line_number=10,
    )
    defaults.update(kwargs)
    return ReviewComment(**defaults)


def test_format_summary_no_findings():
    result = ReviewResult(summary="All good.", recommendation="approve")
    output = format_summary(result)
    assert "## Junior Code Review" in output
    assert "All good." in output
    assert "No issues found" in output


def test_format_summary_with_findings():
    result = ReviewResult(
        summary="Found issues.",
        recommendation="comment",
        comments=[_make_comment(severity=Severity.HIGH), _make_comment(severity=Severity.LOW)],
    )
    output = format_summary(result)
    assert "### Findings" in output
    assert "High" in output
    assert "Low" in output
    assert "foo.py:10" in output


def test_format_summary_suggestion():
    result = ReviewResult(
        summary="Issue.",
        comments=[_make_comment(suggestion="Fix it this way")],
    )
    output = format_summary(result)
    assert "Suggestion: Fix it this way" in output


def test_format_inline_comment():
    comment = _make_comment(suggestion="Do this instead")
    output = format_inline_comment(comment)
    assert "HIGH" in output
    assert "[logic]" in output
    assert "Test issue" in output
    assert "**Suggestion:**" in output


def test_format_inline_comment_no_suggestion():
    comment = _make_comment(suggestion=None)
    output = format_inline_comment(comment)
    assert "Suggestion" not in output
