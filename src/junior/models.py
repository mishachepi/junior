"""Deprecated import path — kept as a re-export shim for one version.

The code-review domain models moved to `junior.runbooks.code_review.models`:
they belong to the code-review runbook family, while the framework core
(`junior.runbook`) is domain-agnostic and defines no domain models at all.
Update imports to the new path; this shim will be removed in the next version.
"""

from junior.runbooks.code_review.models import (
    ChangedFile,
    CollectedContext,
    FileStatus,
    LLMReviewOutput,
    MRComment,
    Recommendation,
    ReviewCategory,
    ReviewComment,
    ReviewResult,
    Severity,
    assemble_review_result,
)

__all__ = [
    "ChangedFile",
    "CollectedContext",
    "FileStatus",
    "LLMReviewOutput",
    "MRComment",
    "Recommendation",
    "ReviewCategory",
    "ReviewComment",
    "ReviewResult",
    "Severity",
    "assemble_review_result",
]
