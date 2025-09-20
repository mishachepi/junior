"""Data models for Junior."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class FileStatus(str, Enum):
    """File status in a pull request."""

    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


class Severity(str, Enum):
    """Issue severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReviewCategory(str, Enum):
    """Review comment categories."""

    SECURITY = "security"
    PERFORMANCE = "performance"
    STYLE = "style"
    COMPLEXITY = "complexity"
    LOGIC = "logic"
    DOCUMENTATION = "documentation"
    TESTING = "testing"
    CRITICAL_BUG = "critical_bug"
    NAMING = "naming"
    OPTIMIZATION = "optimization"
    DRY_VIOLATION = "dry_violation"
    KISS_VIOLATION = "kiss_violation"


class FileChange(BaseModel):
    """Represents a file change in a pull request."""

    filename: str = Field(..., description="Path to the file")
    status: FileStatus = Field(..., description="Status of the file change")
    additions: int = Field(0, description="Number of lines added")
    deletions: int = Field(0, description="Number of lines deleted")
    diff: str | None = Field(None, description="Diff content")
    content: str | None = Field(None, description="Full file content")


class ReviewComment(BaseModel):
    """Represents a code review comment."""

    category: ReviewCategory = Field(..., description="Category of the comment")
    message: str = Field(..., description="Comment message")
    filename: str | None = Field(None, description="File the comment relates to")
    line_number: int | None = Field(
        None, description="Line number the comment relates to"
    )
    severity: Severity = Field(Severity.MEDIUM, description="Severity of the issue")
    suggestion: str | None = Field(None, description="Suggested fix or improvement")
    rule: str | None = Field(None, description="Rule or principle violated")


class CodeReviewRequest(BaseModel):
    """Request for code review."""

    repository: str = Field(..., description="Repository name (owner/repo)")
    pr_number: int = Field(..., description="Pull request number")
    title: str = Field(..., description="Pull request title")
    description: str | None = Field(None, description="Pull request description")
    author: str = Field(..., description="Pull request author")
    base_branch: str = Field("main", description="Base branch")
    head_branch: str = Field(..., description="Head branch")
    files: list[FileChange] = Field(..., description="List of changed files")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CodeReviewResult(BaseModel):
    """Result of code review."""

    pr_number: int = Field(..., description="Pull request number")
    repository: str = Field(..., description="Repository name")
    comments: list[ReviewComment] = Field(..., description="Review comments")
    summary: str = Field(..., description="Overall review summary")
    approved: bool = Field(False, description="Whether the PR is approved")

    # Issue counts by category
    security_issues_count: int = Field(0, description="Number of security issues")
    performance_issues_count: int = Field(0, description="Number of performance issues")
    style_issues_count: int = Field(0, description="Number of style issues")
    complexity_issues_count: int = Field(0, description="Number of complexity issues")

    reviewed_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def total_issues(self) -> int:
        """Total number of issues found."""
        return len(self.comments)

    @property
    def critical_issues(self) -> list[ReviewComment]:
        """Get critical issues."""
        return [c for c in self.comments if c.severity == Severity.CRITICAL]

    @property
    def high_issues(self) -> list[ReviewComment]:
        """Get high severity issues."""
        return [c for c in self.comments if c.severity == Severity.HIGH]


class ReviewData(BaseModel):
    """Essential data structure for code review."""

    repository: str = Field(..., description="Repository name (owner/repo)")
    pr_number: int = Field(..., description="Pull request number")
    title: str = Field(..., description="PR title")
    description: str | None = Field(None, description="PR description")
    author: str = Field(..., description="PR author username")
    base_branch: str = Field(..., description="Base branch")
    head_branch: str = Field(..., description="Head branch")
    base_sha: str = Field(..., description="Base commit SHA")
    head_sha: str = Field(..., description="Head commit SHA")
    diff_url: str = Field(..., description="GitHub diff URL")
    clone_url: str = Field(..., description="Repository clone URL")
