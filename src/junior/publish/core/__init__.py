"""Core utilities shared across all publisher backends."""

from junior.publish.core.formatter import format_inline_comment, format_summary

MAX_INLINE_COMMENTS = 30  # limit for GitLab/GitHub inline comments per review

__all__ = ["MAX_INLINE_COMMENTS", "format_summary", "format_inline_comment"]
