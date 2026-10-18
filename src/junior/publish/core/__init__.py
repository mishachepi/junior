"""Core utilities shared across all publisher backends."""

from junior.publish.core.formatter import format_inline_comment, format_summary

MAX_INLINE_COMMENTS = 30  # inline comments per review, every platform

__all__ = ["MAX_INLINE_COMMENTS", "format_inline_comment", "format_summary"]
