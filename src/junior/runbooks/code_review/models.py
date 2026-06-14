"""Data models and shared constants for the code-review runbook family.

These are *domain* models — the framework core (`junior.runbook`) is
domain-agnostic and never imports them. They're shared by the code-review
runbooks and their helper libs `junior.collect.*` / `junior.publish.*`.
The old `junior.models` path still works for one version (re-export shim).
"""

from enum import Enum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReviewCategory(str, Enum):
    """Category of a review finding."""
    LOGIC = "logic"
    SECURITY = "security"
    BUG = "bug"
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


class MRComment(BaseModel):
    """A single comment/note on an MR or PR.

    Covers general discussion notes and inline review comments. file_path/line_number
    are populated for inline (positioned) comments only.
    """

    model_config = ConfigDict(frozen=True)

    author: str = ""
    body: str = ""
    created_at: str = ""
    file_path: str | None = None
    line_number: int | None = None
    resolved: bool = False


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

    # Discussion: notes + inline review comments (human only, system notes filtered out)
    comments: list[MRComment] = Field(default_factory=list)

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


class LLMReviewOutput(BaseModel):
    """Schema for a code review submitted by an AI agent."""

    summary: str
    recommendation: Recommendation = Recommendation.COMMENT
    comments: list[ReviewComment] = Field(default_factory=list)


class ReviewResult(BaseModel):
    """Assembled review — LLM output (summary/recommendation/comments) plus runtime metadata we measure."""

    summary: str
    recommendation: Recommendation = Recommendation.COMMENT
    comments: list[ReviewComment] = Field(default_factory=list)
    tokens_used: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    review_errors: list[str] = Field(default_factory=list)
    pre_formatted: str | None = None  # pre-formatted markdown, bypasses format_summary

    @property
    def critical_count(self) -> int:
        return sum(1 for c in self.comments if c.severity == Severity.CRITICAL)

    @property
    def high_count(self) -> int:
        return sum(1 for c in self.comments if c.severity == Severity.HIGH)

    @property
    def has_blocking_issues(self) -> bool:
        return self.critical_count > 0 or self.recommendation == Recommendation.REQUEST_CHANGES


def assemble_review_result(
    review: LLMReviewOutput,
    *,
    tokens_used: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    review_errors: list[str] | None = None,
) -> ReviewResult:
    """Build the runbook result from LLM output plus runtime metadata measured by us."""
    return ReviewResult(
        summary=review.summary,
        recommendation=review.recommendation,
        comments=review.comments,
        tokens_used=tokens_used,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        review_errors=review_errors or [],
    )
