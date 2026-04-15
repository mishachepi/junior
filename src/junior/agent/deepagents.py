"""AI agent for code review using Deep Agents.

The agent can explore the repository, delegate specialized analysis to subagents,
and produce a structured review report via the `submit_review` tool.
"""

import structlog
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage
from langchain_core.outputs import LLMResult
from langchain_core.tools import StructuredTool

from junior.config import Settings
from junior.models import (
    CollectedContext,
    ReviewResult,
)
from junior.agent.core import BASE_RULES, build_user_message, read_project_instructions
from junior.prompt_loader import Prompt


logger = structlog.get_logger()


class _TokenCounter(BaseCallbackHandler):
    """Counts total tokens across all LLM calls."""

    total_tokens: int = 0

    def on_llm_end(self, response: LLMResult, **kwargs) -> None:
        for generations in response.generations:
            for gen in generations:
                tokens = 0
                # Try generation_info first (older langchain)
                usage = getattr(gen, "generation_info", {}) or {}
                token_usage = usage.get("token_usage") or usage.get("usage") or {}
                tokens = token_usage.get("total_tokens", 0)
                # Fallback to message usage_metadata (newer langchain)
                if not tokens:
                    msg = getattr(gen, "message", None)
                    if msg and hasattr(msg, "usage_metadata") and msg.usage_metadata:
                        meta = msg.usage_metadata
                        tokens = meta.get("total_tokens", 0)
                if tokens:
                    self.total_tokens += tokens
                else:
                    logger.debug("could not extract token count from LLM response")


# JSON output instructions appended to each subagent prompt for deepagents
_SUBAGENT_OUTPUT_INSTRUCTIONS = """

Return your findings as a JSON array:
[{"category": "<category>", "severity": "critical|high|medium|low", "message": "...", "file_path": "...", "line_number": N, "suggestion": "..."}]

If no issues found, return an empty array: []
"""


def _make_submit_review_tool() -> tuple[StructuredTool, list[ReviewResult]]:
    """Create a submit_review tool and a capture container."""
    captured: list[ReviewResult] = []

    def submit_review(**kwargs) -> str:
        """Submit the final synthesized code review. Call exactly once after all subagents complete."""
        result = ReviewResult(**kwargs)
        captured.append(result)
        return f"Review submitted: {result.recommendation.value}, {len(result.comments)} comments."

    tool = StructuredTool.from_function(
        func=submit_review,
        name="submit_review",
        args_schema=ReviewResult,
        handle_validation_error=True,
    )
    return tool, captured


def review(context: CollectedContext, settings: Settings, prompts: list[Prompt]) -> ReviewResult:
    """Run AI review using Deep Agents. Returns structured ReviewResult."""
    model_str = settings.model_string
    submit_tool, captured = _make_submit_review_tool()

    # Build subagent definitions from prompts
    subagents = [
        {
            "name": p.name,
            "description": p.description,
            "system_prompt": p.body + _SUBAGENT_OUTPUT_INSTRUCTIONS,
            "tools": [],
        }
        for p in prompts
    ]

    logger.info(
        "invoking deep agent review",
        model=model_str,
        subagents=[p.name for p in prompts],
        changed_files=len(context.changed_files),
    )

    backend = FilesystemBackend(root_dir=settings.ci_project_dir)
    token_counter = _TokenCounter()

    agent = create_deep_agent(
        model=model_str,
        tools=[submit_tool],
        system_prompt=_build_orchestrator_prompt(settings, prompts),
        subagents=subagents,
        backend=backend,
    )

    agent.invoke(
        {"messages": [HumanMessage(content=build_user_message(context))]},
        config={"callbacks": [token_counter]},
    )

    if len(captured) > 1:
        logger.warning("agent called submit_review multiple times, using first result")

    if captured:
        result = captured[0]
        result.tokens_used = token_counter.total_tokens
        logger.info(
            "review captured via submit_review tool",
            comments=len(result.comments),
            tokens=result.tokens_used,
        )
        return result

    raise RuntimeError(
        "DeepAgents agent completed without calling submit_review — "
        f"no review produced ({token_counter.total_tokens} tokens used)"
    )


def _build_orchestrator_prompt(settings: Settings, prompts: list[Prompt]) -> str:
    """Build the orchestrator's system prompt dynamically from loaded prompts."""
    subagent_list = "\n".join(f"   - `{p.name}`: {p.description}" for p in prompts)

    prompt = f"""You are the lead code reviewer orchestrating a thorough review of a merge request.

## Your Workflow

1. **Understand the changes**: Read the diff and MR metadata provided in the user message.
2. **Explore context**: Use `read_file`, `ls`, `grep`, `glob` to understand the codebase around the changed files.
3. **Delegate specialized analysis**: Use the `task` tool to run subagents IN PARALLEL:
{subagent_list}
4. **Synthesize**: Collect all findings, deduplicate, and call `submit_review`.

## Submitting the Final Review

After all subagents complete, call the `submit_review` tool EXACTLY ONCE with the synthesized results.

Valid enum values (use EXACTLY as shown, lowercase):
- `recommendation`: `"approve"` | `"request_changes"` | `"comment"`
- `comments[].severity`: `"low"` | `"medium"` | `"high"` | `"critical"`
- `comments[].category`: `"logic"` | `"security"` | `"critical_bug"` | `"naming"` | `"optimization"` | `"dry_violation"` | `"kiss_violation"`

{BASE_RULES}
"""

    project_instructions = read_project_instructions(settings.ci_project_dir)
    if project_instructions:
        prompt += f"\n## Project-Specific Instructions\n{project_instructions}\n"

    return prompt
