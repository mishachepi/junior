"""Unit tests for the claudecode harness output extraction.

`_extract_output` must handle two CLI shapes: the StructuredOutput tool_use in an
assistant message (older/array output) and the `structured_output` field on the
result message (newer CLI) — and fail loudly when neither is present.
"""

import json

import pytest

from junior.config import LLMSettings, Settings
from junior.harnesses import claudecode as cc
from junior.harnesses.claudecode import _extract_output
from junior.runbooks.code_review.models import ReviewOutput, Recommendation


def test_extract_from_structured_output_tool_use():
    """The classic path: assistant calls the StructuredOutput tool."""
    messages = [
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "StructuredOutput",
             "input": {"summary": "via tool", "recommendation": "approve", "comments": []}},
        ]}},
        {"type": "result", "is_error": False, "usage": {}},
    ]
    out = _extract_output(messages, ReviewOutput)
    assert out.summary == "via tool"
    assert out.recommendation == Recommendation.APPROVE


def test_extract_from_result_structured_output_field():
    """Newer CLI: no tool_use, structured_output lives on the result message."""
    messages = [
        {"type": "system", "subtype": "init"},
        {"type": "result", "is_error": False, "usage": {},
         "structured_output": {"summary": "via result", "recommendation": "comment", "comments": []}},
    ]
    out = _extract_output(messages, ReviewOutput)
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
    assert _extract_output(messages, ReviewOutput).summary == "via tool"


def test_no_structured_output_raises():
    """Claude ended on plain text — clear error, no silent pass."""
    messages = [
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "I cannot help"}]}},
        {"type": "result", "is_error": False, "usage": {}},
    ]
    with pytest.raises(RuntimeError, match="No StructuredOutput"):
        _extract_output(messages, ReviewOutput)


# --- cmd assembly ---------------------------------------------------------


class _FakeProc:
    returncode = 0
    stderr = ""
    stdout = json.dumps([
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "StructuredOutput",
             "input": {"summary": "ok", "recommendation": "approve", "comments": []}},
        ]}},
        {"type": "result", "is_error": False, "usage": {}},
    ])


def _run_and_capture(monkeypatch, settings) -> list[str]:
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakeProc()

    monkeypatch.setattr(cc.subprocess, "run", fake_run)
    cc.HARNESS.complete(
        system_prompt="sys", user_message="usr",
        output_schema=ReviewOutput, settings=settings,
    )
    return captured["cmd"]


def _permission_mode(cmd: list[str]) -> str:
    return cmd[cmd.index("--permission-mode") + 1]


def test_cmd_uses_default_permission_mode(monkeypatch):
    cmd = _run_and_capture(monkeypatch, Settings())
    assert _permission_mode(cmd) == "bypassPermissions"


def test_cmd_uses_configured_permission_mode(monkeypatch):
    settings = Settings(llm=LLMSettings(claudecode={"permission_mode": "acceptEdits"}))
    cmd = _run_and_capture(monkeypatch, settings)
    assert _permission_mode(cmd) == "acceptEdits"
