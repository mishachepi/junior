"""Tests for deepagents harness helpers (no model call)."""

import pytest

from junior.runbooks.code_review.models import ReviewOutput


def test_submit_tool_schema_and_capture():
    """`_make_submit_tool` builds a StructuredTool typed to the output schema and
    captures a *validated* instance when called. This is the deepagents-specific
    surface most likely to break when the result schema changes — and the tool
    construction (`StructuredTool.from_function(args_schema=...)`) is the analog
    of the pydantic-ai tool-build path that previously broke at runtime.
    """
    pytest.importorskip("langchain_core")

    from junior.harnesses.deepagents import _make_submit_tool

    tool, captured = _make_submit_tool(ReviewOutput)

    assert tool.name == "submit_review"
    assert tool.args_schema is ReviewOutput

    tool.func(summary="looks good", recommendation="approve", comments=[])

    assert len(captured) == 1
    assert isinstance(captured[0], ReviewOutput)
    assert captured[0].recommendation == "approve"
