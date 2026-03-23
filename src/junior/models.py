"""Data models and shared constants for Junior code review."""

from enum import Enum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReviewCategory(str, Enum):
    LOGIC = "logic"
    SECURITY = "security"
    CRITICAL_BUG = "critical_bug"
    NAMING = "naming"
    OPTIMIZATION = "optimization"
    DRY_VIOLATION = "dry_violation"
    KISS_VIOLATION = "kiss_violation"


class Recommendation(str, Enum):
    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"
    COMMENT = "comment"


class FileStatus(str, Enum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


class ChangedFile(BaseModel):
    """A single file changed in the MR."""

    model_config = ConfigDict(frozen=True)

    path: str
    status: FileStatus
    diff: str
    content: str | None = None  # full new content (None if deleted)


class CollectedContext(BaseModel):
    """Everything collected deterministically before agent invocation."""

    model_config = ConfigDict(frozen=True)

    # MR metadata
    project_id: int = 0
    mr_iid: int = 0
    mr_title: str = ""
    mr_description: str = ""
    source_branch: str = ""
    target_branch: str = ""
    labels: list[str] = Field(default_factory=list)

    # Commit info
    commit_messages: list[str] = Field(default_factory=list)

    # Collected data
    full_diff: str = ""
    changed_files: list[ChangedFile] = Field(default_factory=list)

    # Extra context from --context KEY="text" and --context-file KEY=path
    extra_context: dict[str, str] = Field(default_factory=dict)


class ReviewComment(BaseModel):
    """A single review comment from the AI agent."""

    model_config = ConfigDict(frozen=True)

    category: ReviewCategory
    severity: Severity
    message: str
    file_path: str | None = None
    line_number: int | None = None
    suggestion: str | None = None

    @model_validator(mode="after")
    def check_line_requires_file(self) -> Self:
        """Discard line_number if file_path is missing."""
        if self.line_number is not None and not self.file_path:
            object.__setattr__(self, "line_number", None)
        return self


class ReviewResult(BaseModel):
    """Complete output from the AI agent."""

    summary: str
    recommendation: Recommendation = Recommendation.COMMENT
    comments: list[ReviewComment] = Field(default_factory=list)
    tokens_used: int = 0  # total tokens across all API calls
    review_errors: list[str] = Field(default_factory=list)

    @property
    def critical_count(self) -> int:
        return sum(1 for c in self.comments if c.severity == Severity.CRITICAL)

    @property
    def high_count(self) -> int:
        return sum(1 for c in self.comments if c.severity == Severity.HIGH)

    @property
    def has_blocking_issues(self) -> bool:
        return self.critical_count > 0 or self.recommendation == Recommendation.REQUEST_CHANGES


def determine_recommendation(comments: list[ReviewComment]) -> Recommendation:
    """Determine recommendation programmatically based on severity.

    Used by agent backends that don't let the LLM decide the recommendation.
    """
    if not comments:
        return Recommendation.APPROVE

    has_critical = any(c.severity == Severity.CRITICAL for c in comments)
    high_count = sum(1 for c in comments if c.severity == Severity.HIGH)
    if has_critical or high_count >= 3:
        return Recommendation.REQUEST_CHANGES

    return Recommendation.COMMENT
