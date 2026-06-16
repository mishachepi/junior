"""Unit tests for the claudecode harness output extraction.

`_extract_output` must handle two CLI shapes: the StructuredOutput tool_use in an
assistant message (older/array output) and the `structured_output` field on the
result message (newer CLI) — and fail loudly when neither is present.
"""

import pytest

from junior.harnesses.claudecode import _extract_output
from junior.runbooks.code_review.models import LLMReviewOutput, Recommendation


def test_extract_from_structured_output_tool_use():
    """The classic path: assistant calls the StructuredOutput tool."""
    messages = [
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "StructuredOutput",
             "input": {"summary": "via tool", "recommendation": "approve", "comments": []}},
        ]}},
        {"type": "result", "is_error": False, "usage": {}},
    ]
    out = _extract_output(messages, LLMReviewOutput)
    assert out.summary == "via tool"
    assert out.recommendation == Recommendation.APPROVE


def test_extract_from_result_structured_output_field():
    """Newer CLI: no tool_use, structured_output lives on the result message."""
    messages = [
        {"type": "system", "subtype": "init"},
        {"type": "result", "is_error": False, "usage": {},
         "structured_output": {"summary": "via result", "recommendation": "comment", "comments": []}},
    ]
    out = _extract_output(messages, LLMReviewOutput)
    assert out.summary == "via result"
    assert out.recommendation == Recommendation.COMMENT


def test_tool_use_takes_precedence_over_result_field():
    """Both present → the tool_use is used (checked first)."""
    messages = [
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "StructuredOutput",
             "input": {"summary": "via tool", "recommendation": "approve", "comments": []}},
        ]}},
        {"type": "result", "is_error": False, "usage": {},
         "structured_output": {"summary": "via result", "recommendation": "comment", "comments": []}},
    ]
    assert _extract_output(messages, LLMReviewOutput).summary == "via tool"


def test_no_structured_output_raises():
    """Claude ended on plain text — clear error, no silent pass."""
    messages = [
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "I cannot help"}]}},
        {"type": "result", "is_error": False, "usage": {}},
    ]
    with pytest.raises(RuntimeError, match="No StructuredOutput"):
        _extract_output(messages, LLMReviewOutput)
