"""Tests for data models."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from junior.models import (
    CodeReviewRequest,
    CodeReviewResult,
    FileChange,
    FileStatus,
    ReviewCategory,
    ReviewComment,
    Severity,
)


class TestFileChange:
    """Tests for FileChange model."""

    def test_file_change_creation(self):
        """Test creating a FileChange."""
        file_change = FileChange(
            filename="test.py",
            status=FileStatus.MODIFIED,
            additions=10,
            deletions=5,
        )

        assert file_change.filename == "test.py"
        assert file_change.status == FileStatus.MODIFIED
        assert file_change.additions == 10
        assert file_change.deletions == 5

    def test_file_change_with_optional_fields(self):
        """Test FileChange with optional fields."""
        file_change = FileChange(
            filename="test.py",
            status=FileStatus.ADDED,
            additions=20,
            deletions=0,
            diff="@@ test diff @@",
            content="print('hello')",
        )

        assert file_change.diff == "@@ test diff @@"
        assert file_change.content == "print('hello')"


class TestReviewComment:
    """Tests for ReviewComment model."""

    def test_review_comment_creation(self):
        """Test creating a ReviewComment."""
        comment = ReviewComment(
            category=ReviewCategory.SECURITY,
            message="Potential SQL injection vulnerability",
            filename="db.py",
            line_number=42,
            severity=Severity.HIGH,
            suggestion="Use parameterized queries",
        )

        assert comment.category == ReviewCategory.SECURITY
        assert comment.message == "Potential SQL injection vulnerability"
        assert comment.filename == "db.py"
        assert comment.line_number == 42
        assert comment.severity == Severity.HIGH
        assert comment.suggestion == "Use parameterized queries"

    def test_review_comment_minimal(self):
        """Test ReviewComment with minimal required fields."""
        comment = ReviewComment(
            category=ReviewCategory.STYLE,
            message="Use consistent naming",
        )

        assert comment.category == ReviewCategory.STYLE
        assert comment.message == "Use consistent naming"
        assert comment.severity == Severity.MEDIUM  # Default


class TestCodeReviewRequest:
    """Tests for CodeReviewRequest model."""

    def test_code_review_request_creation(self, sample_file_change):
        """Test creating a CodeReviewRequest."""
        request = CodeReviewRequest(
            repository="test/repo",
            pr_number=123,
            title="Test PR",
            author="testuser",
            head_branch="feature/test",
            files=[sample_file_change],
        )

        assert request.repository == "test/repo"
        assert request.pr_number == 123
        assert request.title == "Test PR"
        assert request.author == "testuser"
        assert request.base_branch == "main"  # Default
        assert request.head_branch == "feature/test"
        assert len(request.files) == 1
        assert isinstance(request.created_at, datetime)

    def test_code_review_request_validation(self):
        """Test validation of required fields."""
        with pytest.raises(ValidationError):
            CodeReviewRequest(
                # Missing required fields
                repository="test/repo",
            )


class TestCodeReviewResult:
    """Tests for CodeReviewResult model."""

    def test_code_review_result_creation(self):
        """Test creating a CodeReviewResult."""
        comments = [
            ReviewComment(category=ReviewCategory.SECURITY, message="Security issue"),
            ReviewComment(category=ReviewCategory.PERFORMANCE, message="Performance issue"),
        ]

        result = CodeReviewResult(
            pr_number=123,
            repository="test/repo",
            comments=comments,
            summary="Review completed with 2 issues",
            security_issues_count=1,
            performance_issues_count=1,
        )

        assert result.pr_number == 123
        assert result.repository == "test/repo"
        assert len(result.comments) == 2
        assert result.summary == "Review completed with 2 issues"
        assert result.security_issues_count == 1
        assert result.performance_issues_count == 1
        assert not result.approved  # Default
        assert isinstance(result.reviewed_at, datetime)

    def test_total_issues_property(self):
        """Test total_issues property."""
        comments = [
            ReviewComment(category=ReviewCategory.SECURITY, message="Issue 1"),
            ReviewComment(category=ReviewCategory.STYLE, message="Issue 2"),
        ]

        result = CodeReviewResult(
            pr_number=123,
            repository="test/repo",
            comments=comments,
            summary="Test",
        )

        assert result.total_issues == 2

    def test_critical_issues_property(self):
        """Test critical_issues property."""
        comments = [
            ReviewComment(
                category=ReviewCategory.SECURITY,
                message="Critical issue",
                severity=Severity.CRITICAL
            ),
            ReviewComment(
                category=ReviewCategory.STYLE,
                message="Low issue",
                severity=Severity.LOW
            ),
        ]

        result = CodeReviewResult(
            pr_number=123,
            repository="test/repo",
            comments=comments,
            summary="Test",
        )

        critical_issues = result.critical_issues
        assert len(critical_issues) == 1
        assert critical_issues[0].severity == Severity.CRITICAL

    def test_high_issues_property(self):
        """Test high_issues property."""
        comments = [
            ReviewComment(
                category=ReviewCategory.SECURITY,
                message="High issue",
                severity=Severity.HIGH
            ),
            ReviewComment(
                category=ReviewCategory.PERFORMANCE,
                message="High issue 2",
                severity=Severity.HIGH
            ),
            ReviewComment(
                category=ReviewCategory.STYLE,
                message="Medium issue",
                severity=Severity.MEDIUM
            ),
        ]

        result = CodeReviewResult(
            pr_number=123,
            repository="test/repo",
            comments=comments,
            summary="Test",
        )

        high_issues = result.high_issues
        assert len(high_issues) == 2
        assert all(issue.severity == Severity.HIGH for issue in high_issues)
