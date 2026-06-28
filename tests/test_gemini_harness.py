"""Deep tests for the gemini harness (JSON envelope parsing + schema contract)."""

import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

import junior.harnesses.gemini as gemini_mod
from junior.harnesses.gemini import HARNESS, _parse_envelope, _sum_tokens
from junior.config import Settings


class _Out(BaseModel):
    verdict: str
    score: int


def _envelope(response: str, *, models: dict | None = None, error: object = None) -> str:
    obj: dict = {"response": response}
    if models is not None:
        obj["stats"] = {"models": models}
    if error is not None:
        obj["error"] = error
    return json.dumps(obj)


def test_parse_envelope_extracts_response_and_sums_tokens():
    stdout = _envelope(
        '{"verdict": "ok", "score": 5}',
        models={
            "gemini-2.5-pro": {"tokens": {"prompt": 200, "candidates": 30, "total": 230}},
            "gemini-2.5-flash": {"tokens": {"prompt": 10, "candidates": 5, "total": 15}},
        },
    )
    text, usage = _parse_envelope(stdout, 0, "")
    assert text == '{"verdict": "ok", "score": 5}'
    assert usage.input_tokens == 210
    assert usage.output_tokens == 35
    assert usage.total_tokens == 245


def test_sum_tokens_is_defensive_about_shape():
    assert _sum_tokens(None).total_tokens == 0
    assert _sum_tokens({}).total_tokens == 0
    # total falls back to input+output when absent
    usage = _sum_tokens({"models": {"m": {"tokens": {"prompt": 4, "candidates": 6}}}})
    assert usage.total_tokens == 10


def test_parse_envelope_raises_on_envelope_error():
    stdout = _envelope("", error={"message": "quota exceeded"})
    with pytest.raises(RuntimeError, match="quota exceeded"):
        _parse_envelope(stdout, 1, "")


def test_parse_envelope_raises_on_empty_output():
    with pytest.raises(RuntimeError, match="empty output"):
        _parse_envelope("   ", 1, "boom")


def test_parse_envelope_raises_on_non_json():
    with pytest.raises(RuntimeError, match="not valid JSON"):
        _parse_envelope("Gemini CLI error: not authenticated", 1, "")


def test_complete_builds_readonly_command(monkeypatch, tmp_path):
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        stdout = _envelope(
            '{"verdict": "ok", "score": 5}',
            models={"gemini-2.5-pro": {"tokens": {"prompt": 10, "candidates": 5, "total": 15}}},
        )
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(gemini_mod.subprocess, "run", fake_run)
    settings = Settings(
        context={"project_dir": str(tmp_path)},
        llm={"harness": "gemini", "model": "gemini-2.5-pro"},
    )

    result = HARNESS.complete(
        system_prompt="Review.", user_message="diff", output_schema=_Out, settings=settings
    )

    cmd = captured["cmd"]
    assert cmd[0] == "gemini"
    assert cmd[cmd.index("--output-format") + 1] == "json"
    assert cmd[cmd.index("--approval-mode") + 1] == "plan"  # read-only review
    assert "--skip-trust" in cmd
    assert cmd[cmd.index("--model") + 1] == "gemini-2.5-pro"

    prompt = captured["kwargs"]["input"]  # whole prompt on stdin, never argv
    assert prompt.startswith("Review.")
    assert "JSON Schema" in prompt and "verdict" in prompt
    assert prompt.endswith("diff")
    assert captured["kwargs"]["cwd"] == str(tmp_path)

    assert result.output.verdict == "ok"
    assert result.usage.total_tokens == 15


def test_complete_raises_on_failure(monkeypatch, tmp_path):
    def fake_run(cmd, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="not authenticated")

    monkeypatch.setattr(gemini_mod.subprocess, "run", fake_run)
    settings = Settings(context={"project_dir": str(tmp_path)}, llm={"harness": "gemini"})

    with pytest.raises(RuntimeError, match="empty output"):
        HARNESS.complete(
            system_prompt="x", user_message="y", output_schema=_Out, settings=settings
        )
