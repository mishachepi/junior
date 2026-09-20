"""Tests for the pydantic-ai harness."""

import pytest

from junior.config import Settings
from junior.runbooks.code_review.models import ReviewOutput


def test_complete_builds_file_tools_without_namerror(monkeypatch):
    """Regression: the module-level file tools annotate their first parameter as
    ``RunContext[ReviewDeps]``, but ``pydantic_ai`` is imported lazily inside
    ``_run``. With ``from __future__ import annotations`` that annotation is a
    string pydantic-ai resolves at runtime against the module globals — so the
    harness must expose ``RunContext`` there before building the agent, otherwise
    tool-schema generation raises ``NameError: name 'RunContext' is not defined``.

    This drives the real ``Agent`` construction (the failing surface) and stubs
    only the network call.
    """
    pytest.importorskip("pydantic_ai")
    import pydantic_ai

    from junior.harnesses.pydantic import HARNESS

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    class _Usage:
        input_tokens = 11
        output_tokens = 7

    class _Result:
        output = ReviewOutput(summary="looks good", recommendation="approve", comments=[])
        usage = _Usage()

    async def _fake_run(self, *args, **kwargs):  # noqa: ANN001 — stub signature
        return _Result()

    # Real Agent.__init__ (with the file tools) still runs — that's the exact step
    # that raised NameError before the fix; only the model call is stubbed out.
    monkeypatch.setattr(pydantic_ai.Agent, "run", _fake_run)

    settings = Settings.model_validate(
        {
            "llm": {
                "harness": "pydantic",
                "model": "anthropic:claude-sonnet-4-6",
                "anthropic_api_key": "sk-test",
            }
        }
    )

    result = HARNESS.complete(
        system_prompt="You are a code reviewer.",
        user_message="diff goes here",
        output_schema=ReviewOutput,
        settings=settings,
    )

    assert result.output.recommendation == "approve"
    assert result.usage.input_tokens == 11
    assert result.usage.output_tokens == 7
    assert result.usage.total_tokens == 18


# --- _translate_error: SDK exceptions become actionable messages ---


def _http_error(status_code: int, body: object):
    from pydantic_ai.exceptions import ModelHTTPError

    return ModelHTTPError(status_code=status_code, model_name="test-model", body=body)


@pytest.mark.parametrize(
    "body",
    [
        # OpenAI phrasing + nesting
        {"error": {"message": "This model's maximum context length is 128000 tokens.",
                   "code": "context_length_exceeded"}},
        # Anthropic phrasing
        {"error": {"type": "invalid_request_error",
                   "message": "prompt is too long: 250000 tokens > 200000 maximum"}},
    ],
)
def test_translate_error_context_overflow(body):
    pytest.importorskip("pydantic_ai")
    from junior.harnesses.pydantic import _translate_error

    err = _translate_error(_http_error(400, body), "openai:gpt-test")
    assert isinstance(err, RuntimeError)
    assert "input is too large for model 'openai:gpt-test'" in str(err)
    assert "max_diff_chars" in str(err)


def test_translate_error_rate_limit():
    pytest.importorskip("pydantic_ai")
    from junior.harnesses.pydantic import _translate_error

    err = _translate_error(
        _http_error(429, {"error": {"message": "Rate limit reached"}}), "openai:gpt-test"
    )
    assert isinstance(err, RuntimeError)
    assert "rate-limited" in str(err)
    assert "Rate limit reached" in str(err)


def test_translate_error_bad_key():
    pytest.importorskip("pydantic_ai")
    from junior.harnesses.pydantic import _translate_error

    err = _translate_error(_http_error(401, "unauthorized"), "anthropic:claude-test")
    assert isinstance(err, RuntimeError)
    assert "rejected the API key" in str(err)


def test_translate_error_generic_400_is_not_overflow():
    """A 400 without a context-window phrasing stays a generic HTTP failure."""
    pytest.importorskip("pydantic_ai")
    from junior.harnesses.pydantic import _translate_error

    err = _translate_error(
        _http_error(400, {"error": {"message": "invalid request"}}), "openai:gpt-test"
    )
    assert isinstance(err, RuntimeError)
    assert "input is too large" not in str(err)
    assert "call failed (HTTP 400)" in str(err)


def test_translate_error_usage_limit():
    pytest.importorskip("pydantic_ai")
    from pydantic_ai.exceptions import UsageLimitExceeded

    from junior.harnesses.pydantic import _translate_error

    err = _translate_error(UsageLimitExceeded("output exceeded"), "openai:gpt-test")
    assert isinstance(err, RuntimeError)
    assert "max_tokens_per_agent" in str(err)


def test_translate_error_unknown_returns_none():
    """Unrecognized exceptions must re-raise as-is — no information lost."""
    pytest.importorskip("pydantic_ai")
    from junior.harnesses.pydantic import _translate_error

    assert _translate_error(ValueError("boom"), "openai:gpt-test") is None


def test_run_wraps_model_http_error(monkeypatch):
    """End-to-end through complete(): agent.run raising ModelHTTPError surfaces
    as the friendly RuntimeError, chained to the original."""
    pytest.importorskip("pydantic_ai")
    import pydantic_ai
    from pydantic_ai.exceptions import ModelHTTPError

    from junior.harnesses.pydantic import HARNESS

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    async def _fake_run(self, *args, **kwargs):  # noqa: ANN001 — stub signature
        raise ModelHTTPError(
            status_code=400,
            model_name="claude-test",
            body={"error": {"message": "prompt is too long: 250000 tokens > 200000 maximum"}},
        )

    monkeypatch.setattr(pydantic_ai.Agent, "run", _fake_run)

    settings = Settings.model_validate(
        {
            "llm": {
                "harness": "pydantic",
                "model": "anthropic:claude-test",
                "anthropic_api_key": "sk-test",
            }
        }
    )

    with pytest.raises(RuntimeError, match="input is too large") as exc_info:
        HARNESS.complete(
            system_prompt="You are a code reviewer.",
            user_message="diff goes here",
            output_schema=ReviewOutput,
            settings=settings,
        )
    assert isinstance(exc_info.value.__cause__, ModelHTTPError)
