"""Deep tests for the pi harness (JSON event-stream parsing + schema contract)."""

import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

import junior.harnesses.pi as pi_mod
from junior.config import Settings
from junior.harnesses.pi import HARNESS, _last_assistant, _parse_response


class _Out(BaseModel):
    verdict: str
    score: int


def _event(role: str, text: str, usage: dict | None = None) -> str:
    message = {"role": role, "content": [{"type": "text", "text": text}]}
    if usage is not None:
        message["usage"] = usage
    return json.dumps({"type": "message_end", "message": message})


def test_last_assistant_takes_final_text_and_sums_usage():
    stdout = "\n".join([
        '{"type":"session","version":3}',
        '{"type":"agent_start"}',
        _event("user", "review this"),
        # turn 1: tool round-trip — empty text, usage still counts
        _event("assistant", "", {"input": 100, "output": 20, "cacheRead": 50, "cacheWrite": 0}),
        # turn 2: the answer
        _event("assistant", '{"verdict": "ok", "score": 5}',
               {"input": 200, "output": 30, "cacheRead": 0, "cacheWrite": 10}),
        '{"type":"agent_end","messages":[]}',
    ])
    text, usage = _last_assistant(stdout)
    assert text == '{"verdict": "ok", "score": 5}'
    assert usage.input_tokens == 100 + 50 + 200 + 10
    assert usage.output_tokens == 50
    assert usage.total_tokens == usage.input_tokens + usage.output_tokens


def test_last_assistant_ignores_garbage_lines():
    stdout = "warning: something\n{not json}\n" + _event("assistant", "hi", {"input": 1, "output": 2})
    text, usage = _last_assistant(stdout)
    assert text == "hi"
    assert usage.total_tokens == 3


def test_parse_response_strict_json():
    out = _parse_response('{"verdict": "ok", "score": 5}', _Out)
    assert out.verdict == "ok" and out.score == 5


def test_parse_response_tolerates_fences_and_prose():
    out = _parse_response(
        'Here is my answer:\n```json\n{"verdict": "bad", "score": 1}\n```\nDone.', _Out
    )
    assert out.verdict == "bad" and out.score == 1


def test_parse_response_rejects_non_json():
    with pytest.raises(RuntimeError, match="JSON"):
        _parse_response("I could not produce JSON, sorry.", _Out)


def test_parse_response_rejects_schema_mismatch():
    with pytest.raises(RuntimeError, match="validation"):
        _parse_response('{"verdict": "ok"}', _Out)  # missing required `score`


def test_complete_builds_hermetic_command(monkeypatch, tmp_path):
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        stdout = _event("assistant", '{"verdict": "ok", "score": 5}',
                        {"input": 10, "output": 5, "cacheRead": 0, "cacheWrite": 0})
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(pi_mod.subprocess, "run", fake_run)
    settings = Settings(
        context={"project_dir": str(tmp_path)}, llm={"harness": "pi", "model": "anthropic/x"}
    )

    result = HARNESS.complete(
        system_prompt="Review.", user_message="diff", output_schema=_Out, settings=settings
    )

    cmd = captured["cmd"]
    assert cmd[:3] == ["pi", "--mode", "json"]
    for flag in ("--no-session", "--no-extensions", "--no-skills",
                 "--no-prompt-templates", "--no-context-files"):
        assert flag in cmd
    assert cmd[cmd.index("--tools") + 1] == "read,grep,find,ls"
    assert cmd[cmd.index("--model") + 1] == "anthropic/x"
    assert cmd[-1] == "diff"                       # user message is the positional arg
    sys_prompt = cmd[cmd.index("--system-prompt") + 1]
    assert sys_prompt.startswith("Review.")
    assert "JSON Schema" in sys_prompt and "verdict" in sys_prompt
    assert captured["kwargs"]["env"]["PI_OFFLINE"] == "1"
    assert captured["kwargs"]["cwd"] == str(tmp_path)

    assert result.output.verdict == "ok"
    assert result.usage.total_tokens == 15


def test_complete_raises_on_failure_without_text(monkeypatch, tmp_path):
    def fake_run(cmd, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(pi_mod.subprocess, "run", fake_run)
    settings = Settings(context={"project_dir": str(tmp_path)}, llm={"harness": "pi"})

    with pytest.raises(RuntimeError, match="pi CLI failed"):
        HARNESS.complete(
            system_prompt="x", user_message="y", output_schema=_Out, settings=settings
        )
