"""Shared finalisation for collected MR/PR comments.

Every collector backend (gitlab/github/bitbucket) parses platform-specific
payloads into `MRComment`s and then finalises the list identically: drop empty
bodies, sort oldest→newest, keep the newest `MAX_COMMENTS`. That shared tail
lives here — the collect-side mirror of `publish/core`'s `MAX_INLINE_COMMENTS`.
"""

from __future__ import annotations

from junior.runbooks.code_review.models import MRComment

# Cap on how many human comments we send to the LLM (newest kept, oldest first).
MAX_COMMENTS = 50


def finalize_comments(comments: list[MRComment]) -> list[MRComment]:
    """Drop empty-body comments, sort oldest→newest, keep the newest MAX_COMMENTS."""
    kept = [c for c in comments if c.body.strip()]
    kept.sort(key=lambda c: c.created_at)
    if len(kept) > MAX_COMMENTS:
        kept = kept[-MAX_COMMENTS:]
    return kept
