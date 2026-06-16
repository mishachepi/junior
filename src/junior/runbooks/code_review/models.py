"""Data models and shared constants for the code-review runbook family.

These are *domain* models — the framework core (`junior.runbook`) is
domain-agnostic and never imports them. They're shared by the code-review
runbooks and their helper libs `junior.collect.*` / `junior.publish.*`.
The old `junior.models` path still works for one version (re-export shim).
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from junior.runbook.base import LLMResult, Usage


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


class ReviewContext(BaseModel):
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

    @model_validator(mode="before")
    @classmethod
    def _drop_orphan_line(cls, data):
        """Drop a line_number that has no file_path — meaningless for an inline
        comment. Normalising *before* construction keeps the model truly frozen
        (no object.__setattr__ on an already-built instance)."""
        if (
            isinstance(data, dict)
            and data.get("line_number") is not None
            and not data.get("file_path")
        ):
            return {**data, "line_number": None}
        return data


class ReviewOutput(BaseModel):
    """The review the LLM submits — the runbook's output schema (`result_model`).

    A clean contract with the model: summary + recommendation + findings, plus
    the derived counting/blocking logic that lives on the owner of those fields.
    """

    model_config = ConfigDict(frozen=True)

    summary: str
    recommendation: Recommendation = Recommendation.COMMENT
    comments: list[ReviewComment] = Field(default_factory=list)

    @property
    def critical_count(self) -> int:
        return sum(1 for c in self.comments if c.severity == Severity.CRITICAL)

    @property
    def high_count(self) -> int:
        return sum(1 for c in self.comments if c.severity == Severity.HIGH)

    @property
    def has_blocking_issues(self) -> bool:
        return self.critical_count > 0 or self.recommendation == Recommendation.REQUEST_CHANGES


class ReviewResult(LLMResult):
    """Assembled review: the LLM `output` plus the runtime metadata we measure.

    A thin domain extension of the framework envelope `LLMResult` — it reuses
    `output`/`usage`/`errors` (no flat duplication) and narrows `output` to the
    code-review schema, adding only the domain-specific `pre_formatted`.
    """

    model_config = ConfigDict(frozen=True)

    output: ReviewOutput
    pre_formatted: str | None = None  # pre-formatted markdown, bypasses format_summary


def assemble_review_result(
    output: ReviewOutput,
    *,
    usage: Usage,
    errors: list[str] | None = None,
) -> ReviewResult:
    """Build the runbook result from LLM output plus the runtime metadata we measure."""
    return ReviewResult(output=output, usage=usage, errors=errors or [])
