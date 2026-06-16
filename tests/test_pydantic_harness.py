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

        def usage(self):
            return _Usage()

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
