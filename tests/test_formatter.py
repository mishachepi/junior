"""Tests for formatter: summary and inline comment formatting."""

from junior.config import HarnessKind, LLMSettings, Settings
from junior.publish.core import format_inline_comment, format_summary
from junior.runbook.base import Usage
from junior.runbooks.code_review.models import (
    ReviewCategory,
    ReviewComment,
    ReviewOutput,
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


def _result(*, usage: Usage | None = None, **output_kwargs) -> ReviewResult:
    return ReviewResult(output=ReviewOutput(**output_kwargs), usage=usage or Usage())


def test_format_summary_no_findings():
    result = _result(summary="All good.", recommendation="approve")
    output = format_summary(result)
    assert "## Junior Code Review" in output
    assert "All good." in output
    assert "No issues found" in output


def test_format_summary_with_findings():
    result = _result(
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
    result = _result(
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


def test_format_summary_footer_shows_split_tokens_and_explicit_claude_model():
    result = _result(
        summary="All good.",
        usage=Usage(input_tokens=1200, output_tokens=300, total_tokens=1500),
    )
    settings = Settings(
        llm=LLMSettings(
            harness=HarnessKind.CLAUDECODE, model="claude-sonnet-4-6"
        )
    )

    output = format_summary(result, settings)

    assert "claudecode" in output
    assert "claude-sonnet-4-6" in output
    assert "1,200 in / 300 out tokens" in output
    assert "1,500 tokens" not in output


def test_format_summary_footer_hides_model_for_codex():
    result = _result(summary="All good.", usage=Usage(total_tokens=1500))
    settings = Settings(
        llm=LLMSettings(harness=HarnessKind.CODEX, model="gpt-5.4")
    )

    output = format_summary(result, settings)

    assert "codex" in output
    assert "gpt-5.4" not in output
    assert "1,500 tokens" in output
