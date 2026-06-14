"""Deep Agents engine.

An orchestrator that can explore the repository and submits its final result via
a `submit_review` tool whose schema is the requested output model.
"""

from __future__ import annotations

import os

import structlog
from pydantic import BaseModel

from junior.config import Settings
from junior.runbook.base import EnvVar, Harness, LLMResult, Usage

logger = structlog.get_logger()


def _make_token_counter():
    """Build a LangChain callback that tallies tokens across LLM calls.

    Defined lazily so `langchain_core` is imported only when a review actually
    runs — importing this module (e.g. for `junior list`) stays cheap.
    """
    from langchain_core.callbacks import BaseCallbackHandler

    class _TokenCounter(BaseCallbackHandler):
        input_tokens: int = 0
        output_tokens: int = 0

        @property
        def total_tokens(self) -> int:
            return self.input_tokens + self.output_tokens

        def on_llm_end(self, response, **kwargs) -> None:
            for generations in response.generations:
                for gen in generations:
                    msg = getattr(gen, "message", None)
                    meta = getattr(msg, "usage_metadata", None) if msg else None
                    if meta:
                        self.input_tokens += meta.get("input_tokens", 0)
                        self.output_tokens += meta.get("output_tokens", 0)
                        continue
                    usage = (getattr(gen, "generation_info", {}) or {}).get("token_usage") or {}
                    if usage:
                        self.input_tokens += usage.get("prompt_tokens", 0)
                        self.output_tokens += usage.get("completion_tokens", 0)
                    else:
                        logger.debug("could not extract token count from LLM response")

    return _TokenCounter()


_SUBMIT_INSTRUCTIONS = """

## Submitting the Final Result

Explore the changes and surrounding code, then call the `submit_review` tool
EXACTLY ONCE with your synthesized result. Do not call it more than once.
"""


def _make_submit_tool(output_schema: type[BaseModel]) -> tuple["object", list[BaseModel]]:
    """Create a submit tool whose args_schema is `output_schema` + a capture list."""
    from langchain_core.tools import StructuredTool

    captured: list[BaseModel] = []

    def submit_review(**kwargs) -> str:
        """Submit the final synthesized result. Call exactly once."""
        obj = output_schema(**kwargs)
        captured.append(obj)
        return "Result submitted."

    tool = StructuredTool.from_function(
        func=submit_review,
        name="submit_review",
        args_schema=output_schema,
        handle_validation_error=True,
    )
    return tool, captured


class DeepAgentsHarness(Harness):
    name = "deepagents"
    file_access = False  # gets context inline; FilesystemBackend is for exploration
    env_vars = (
        EnvVar(
            "OPENAI_API_KEY / ANTHROPIC_API_KEY", True,
            "LLM provider key (matches your model's provider)",
        ),
    )

    def is_ready(self) -> str:
        if os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"):
            return "ready"
        return "not ready: set OPENAI_API_KEY / ANTHROPIC_API_KEY"

    def complete(
        self,
        *,
        system_prompt: str,
        user_message: str,
        output_schema: type[BaseModel],
        settings: Settings,
    ) -> LLMResult:
        from deepagents import create_deep_agent
        from deepagents.backends import FilesystemBackend
        from langchain_core.messages import HumanMessage

        model_str = settings.llm.model_string
        submit_tool, captured = _make_submit_tool(output_schema)
        backend = FilesystemBackend(root_dir=str(settings.context.project_dir))
        token_counter = _make_token_counter()

        logger.debug("invoking deep agent", model=model_str, schema=output_schema.__name__)

        agent = create_deep_agent(
            model=model_str,
            tools=[submit_tool],
            system_prompt=system_prompt + _SUBMIT_INSTRUCTIONS,
            backend=backend,
        )
        agent.invoke(
            {"messages": [HumanMessage(content=user_message)]},
            config={"callbacks": [token_counter]},
        )

        if len(captured) > 1:
            logger.warning("agent called submit_review multiple times, using first result")
        if not captured:
            raise RuntimeError(
                "DeepAgents agent completed without calling submit_review — "
                f"no result produced ({token_counter.total_tokens} tokens used)"
            )

        return LLMResult(
            output=captured[0],
            usage=Usage(
                input_tokens=token_counter.input_tokens,
                output_tokens=token_counter.output_tokens,
                total_tokens=token_counter.total_tokens,
            ),
        )


HARNESS = DeepAgentsHarness()
