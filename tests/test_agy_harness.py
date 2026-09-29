"""Deep tests for the agy (Antigravity CLI) harness: envelope parsing + command shape."""

import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

import junior.harnesses._shared as shared
from junior.config import Settings
from junior.harnesses.agy import HARNESS, _extract_output, _parse_envelope, _usage


class _Out(BaseModel):
    verdict: str
    score: int


def _envelope(**fields) -> str:
    obj: dict = {"conversation_id": "c1", "status": "SUCCESS", "response": "", "num_turns": 1}
    obj.update(fields)
    return json.dumps(obj)


def test_parse_envelope_returns_successful_turn():
    data = _parse_envelope(_envelope(response="hi"), 0, "")
    assert data["response"] == "hi"


def test_parse_envelope_raises_on_error_field_and_bad_status():
    with pytest.raises(RuntimeError, match="quota exceeded"):
        _parse_envelope(_envelope(status="ERROR", error={"message": "quota exceeded"}), 1, "")
    with pytest.raises(RuntimeError, match="status FAILED"):
        _parse_envelope(_envelope(status="FAILED"), 1, "stderr tail")


def test_parse_envelope_raises_on_empty_or_non_json():
    with pytest.raises(RuntimeError, match="empty output"):
        _parse_envelope("   ", 1, "boom")
    with pytest.raises(RuntimeError, match="not valid JSON"):
        _parse_envelope("Please log in first", 1, "")


def test_extract_output_prefers_structured_output():
    data = json.loads(_envelope(
        response='prose then {"verdict": "text", "score": 1}',
        structured_output={"verdict": "ok", "score": 5},
    ))
    assert _extract_output(data, _Out).verdict == "ok"


def test_extract_output_falls_back_to_text_reply():
    data = json.loads(_envelope(response='```json\n{"verdict": "ok", "score": 5}\n```'))
    assert _extract_output(data, _Out).score == 5


def test_extract_output_names_the_denied_action():
    """Headless auto-deny: status SUCCESS, empty response, denied_actions — must
    fail loudly with the action, not with a generic validation error."""
    data = json.loads(_envelope(
        denied_actions=[{"action": "command", "display_name": "RunCommand"}],
    ))
    with pytest.raises(RuntimeError, match="auto-denied: RunCommand"):
        _extract_output(data, _Out)


def test_usage_is_defensive_about_shape():
    assert _usage(None).total_tokens == 0
    usage = _usage({"input_tokens": 100, "output_tokens": 20, "thinking_tokens": 15,
                    "cache_read_tokens": 0, "total_tokens": 120})
    assert (usage.input_tokens, usage.output_tokens, usage.total_tokens) == (100, 20, 120)
    assert _usage({"input_tokens": 4, "output_tokens": 6}).total_tokens == 10


def test_complete_builds_headless_command(monkeypatch, tmp_path):
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            returncode=0,
            stdout=_envelope(
                response="ok",
                structured_output={"verdict": "ok", "score": 5},
                usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            ),
            stderr="",
        )

    monkeypatch.setattr(shared.subprocess, "run", fake_run)
    settings = Settings(
        context={"project_dir": str(tmp_path)},
        llm={"harness": "agy", "model": "gemini-3.1-pro-high"},
    )

    result = HARNESS.complete(
        system_prompt="Review.", user_message="diff", output_schema=_Out, llm=settings.llm, project_dir=settings.context.project_dir
    )

    cmd = captured["cmd"]
    assert cmd[0] == "agy"
    prompt_arg = next(a for a in cmd if a.startswith("--print="))
    prompt = prompt_arg.removeprefix("--print=")
    assert prompt.startswith("Review.") and prompt.endswith("diff")  # system + user, argv
    assert "without a shell" in prompt  # headless note: no commands, file tools only
    assert cmd[cmd.index("--output-format") + 1] == "json"
    schema = json.loads(cmd[cmd.index("--json-schema") + 1])
    assert set(schema["required"]) == {"verdict", "score"}  # native schema, not in prompt
    assert "JSON Schema" not in prompt
    assert cmd[cmd.index("--model") + 1] == "gemini-3.1-pro-high"
    assert captured["kwargs"]["cwd"] == str(tmp_path)
    assert captured["kwargs"].get("input") is None  # agy reads no prompt from stdin

    assert result.output.verdict == "ok"
    assert result.usage.total_tokens == 15


def test_complete_raises_on_failure(monkeypatch, tmp_path):
    def fake_run(cmd, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="not logged in")

    monkeypatch.setattr(shared.subprocess, "run", fake_run)
    settings = Settings(context={"project_dir": str(tmp_path)}, llm={"harness": "agy"})

    with pytest.raises(RuntimeError, match="empty output"):
        HARNESS.complete(
            system_prompt="x", user_message="y", output_schema=_Out, llm=settings.llm, project_dir=settings.context.project_dir
        )
