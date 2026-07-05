"""Direct unit tests for the generic runner.

`run_runbook()` is the coordination seam: collect (caller's concern) → render →
harness.complete → optional publish. Integration tests exercise it end-to-end
with the real code_review runbook; these lock the *contract* with fakes so a
change to the signature or the collect→harness→publish wiring fails loudly here.
"""

from __future__ import annotations

from pydantic import BaseModel

from junior.config import Settings
from junior.runbook.base import Harness, LLMResult, Runbook, Usage
from junior.runbook.runner import run_runbook


class _Ctx(BaseModel):
    pass


class _Res(BaseModel):
    verdict: str = "ok"


class _RecordingHarness(Harness):
    """Records the kwargs `complete()` is called with; returns a fixed result."""

    name = "recording"
    file_access = True

    def __init__(self, result: LLMResult):
        self._result = result
        self.complete_calls: list[dict] = []

    def complete(self, *, system_prompt, user_message, output_schema, settings):
        self.complete_calls.append(
            {
                "system_prompt": system_prompt,
                "user_message": user_message,
                "output_schema": output_schema,
                "settings": settings,
            }
        )
        return self._result


class _RecordingRunbook(Runbook):
    name = "recording"
    context_model = _Ctx
    result_model = _Res
    SYSTEM_PROMPT = "you are a test runbook"

    def __init__(self):
        self.render_calls: list[dict] = []
        self.publish_calls: list[dict] = []

    def collect(self, settings):  # not exercised by run_runbook (caller collects)
        return _Ctx()

    def render(self, context, settings, *, file_access):
        self.render_calls.append({"context": context, "file_access": file_access})
        return "rendered-user-message"

    def publish(self, settings, result, usage, *, errors):
        self.publish_calls.append({"result": result, "usage": usage, "errors": errors})


def _make() -> tuple[_RecordingRunbook, _RecordingHarness, LLMResult]:
    result = LLMResult(
        output=_Res(verdict="done"),
        usage=Usage(input_tokens=5, output_tokens=3, total_tokens=8),
        errors=["partial-failure-note"],
    )
    return _RecordingRunbook(), _RecordingHarness(result), result


def test_run_runbook_threads_context_through_harness():
    runbook, harness, result = _make()
    settings = Settings()

    returned = run_runbook(runbook, harness, _Ctx(), settings, publish_enabled=False)

    # returns the harness result verbatim
    assert returned is result
    # render was asked exactly once, with the harness's own file_access flag
    assert len(runbook.render_calls) == 1
    assert runbook.render_calls[0]["file_access"] is True
    # complete got the runbook's system prompt, the rendered message, and the
    # runbook's result_model as the output schema
    call = harness.complete_calls[0]
    assert call["user_message"] == "rendered-user-message"
    assert call["output_schema"] is _Res
    assert call["settings"] is settings
    assert "you are a test runbook" in call["system_prompt"]


def test_run_runbook_publishes_when_enabled():
    runbook, harness, result = _make()

    run_runbook(runbook, harness, _Ctx(), Settings(), publish_enabled=True)

    assert len(runbook.publish_calls) == 1
    published = runbook.publish_calls[0]
    # publish receives the LLM output, its usage, and the harness's error notes
    assert published["result"] is result.output
    assert published["usage"] is result.usage
    assert published["errors"] == ["partial-failure-note"]


def test_run_runbook_skips_publish_when_disabled():
    runbook, harness, result = _make()

    returned = run_runbook(runbook, harness, _Ctx(), Settings(), publish_enabled=False)

    assert runbook.publish_calls == []
    assert returned is result  # still returns the result for the CLI to render
