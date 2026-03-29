"""Claude Code CLI implementation of code review agent.

Single subprocess call to `claude -p` — no tool loops, predictable cost.
Claude Code has built-in file tools (Read, Grep, Glob) and read-only
git access, so we pass metadata only — no full diff.
"""

import json
import subprocess

import structlog

from junior.config import Settings
from junior.models import CollectedContext, ReviewResult
from junior.agent.core import build_review_prompt, build_user_message
from junior.prompt_loader import Prompt

logger = structlog.get_logger()

_OUTPUT_SCHEMA = json.dumps(ReviewResult.model_json_schema())

_TOOLS = "Read,Bash(git log:*,git show:*,git diff:*,git blame:*),Grep,Glob"


def review(context: CollectedContext, settings: Settings, prompts: list[Prompt]) -> ReviewResult:
    """Run AI review via claude CLI subprocess."""
    user_prompt = build_user_message(context, include_diff=False)
    system_prompt = build_review_prompt(prompts, settings.ci_project_dir)

    logger.info(
        "invoking claude CLI review",
        model=settings.model_name or None,
        prompts=[p.name for p in prompts],
        changed_files=len(context.changed_files),
    )

    cmd = [
        "claude", "-p",
        "--output-format", "json",
        "--json-schema", _OUTPUT_SCHEMA,
        "--append-system-prompt", system_prompt,
        "--tools", _TOOLS,
        "--permission-mode", "bypassPermissions",
        "--no-session-persistence",
    ]
    if settings.anthropic_api_key:
        cmd.append("--bare")
    if settings.model_name:
        cmd.extend(["--model", settings.model_name])

    try:
        proc = subprocess.run(
            cmd, input=user_prompt, capture_output=True, text=True,
            cwd=settings.ci_project_dir, timeout=600,
        )
    except FileNotFoundError:
        raise RuntimeError("claude CLI not found — install with: npm install -g @anthropic-ai/claude-code")
    except subprocess.TimeoutExpired:
        raise RuntimeError("claude CLI timed out after 10 minutes")

    if proc.returncode != 0:
        if not proc.stdout.strip():
            raise RuntimeError(f"claude CLI failed (exit {proc.returncode}): {(proc.stderr or '')[-500:]}")
        logger.warning("claude CLI exited with non-zero code", returncode=proc.returncode)

    raw = proc.stdout.strip()
    if not raw:
        raise RuntimeError(f"claude CLI returned empty output: {(proc.stderr or '')[-500:]}")

    messages = _parse_messages(raw)
    result_msg = _find_result(messages)

    if result_msg.get("is_error"):
        raise RuntimeError(f"claude CLI error: {result_msg.get('result', 'unknown error')}")

    review_result = _extract_review(messages)
    review_result.tokens_used = _extract_token_usage(result_msg)
    return review_result


# --- Output parsing ---


def _parse_messages(output: str) -> list[dict]:
    """Parse claude streaming JSON output (JSON array of message objects)."""
    try:
        data = json.loads(output)
    except json.JSONDecodeError as e:
        logger.error("claude output is not valid JSON", output=output[:500], error=str(e))
        raise RuntimeError(f"Failed to parse claude output: {e}")

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    raise RuntimeError(f"Unexpected claude output type: {type(data).__name__}")


def _find_result(messages: list[dict]) -> dict:
    """Find the result message in claude output."""
    for msg in reversed(messages):
        if msg.get("type") == "result":
            return msg
    raise RuntimeError("No result message in claude output")


def _extract_review(messages: list[dict]) -> ReviewResult:
    """Extract ReviewResult from StructuredOutput tool_use.

    With --json-schema, claude always returns data via StructuredOutput tool
    as a dict in content[].input.
    """
    for msg in reversed(messages):
        if msg.get("type") != "assistant":
            continue
        for content in msg.get("message", {}).get("content", []):
            if content.get("type") == "tool_use" and content.get("name") == "StructuredOutput":
                return ReviewResult.model_validate(content["input"])

    raise RuntimeError("No StructuredOutput found in claude response")


def _extract_token_usage(result_msg: dict) -> int:
    """Extract total token count from claude result message."""
    usage = result_msg.get("usage", {})
    return (
        usage.get("input_tokens", 0)
        + usage.get("output_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
    )
