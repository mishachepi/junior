"""Deprecated import path — kept as a re-export shim for one version.

The code-review domain models moved to `junior.runbooks.code_review.models`:
they belong to the code-review runbook family, while the framework core
(`junior.runbook`) is domain-agnostic and defines no domain models at all.
Update imports to the new path; this shim will be removed in the next version.

Two models were also renamed in the move (the old names stay as aliases here so
forks importing them keep working for one version):

- `CollectedContext` → `ReviewContext`
- `LLMReviewOutput`  → `ReviewOutput`
"""

from junior.runbooks.code_review.models import (
    ChangedFile,
    FileStatus,
    MRComment,
    Recommendation,
    ReviewCategory,
    ReviewComment,
    ReviewContext,
    ReviewOutput,
    ReviewResult,
    Severity,
    assemble_review_result,
)

# Deprecated aliases for the pre-rename names.
CollectedContext = ReviewContext
LLMReviewOutput = ReviewOutput

__all__ = [
    "ChangedFile",
    "CollectedContext",
    "FileStatus",
    "LLMReviewOutput",
    "MRComment",
    "Recommendation",
    "ReviewCategory",
    "ReviewComment",
    "ReviewContext",
    "ReviewOutput",
    "ReviewResult",
    "Severity",
    "assemble_review_result",
]
