"""Claude Code CLI engine.

Single subprocess call to `claude -p` — no tool loops, predictable cost.
Claude Code has built-in file tools (Read, Grep, Glob) and read-only git access
for context beyond the inlined diff (the code-review runbook drops the diff from
the message only when oversized); the engine just drives the CLI with the
requested output schema.
"""

import json
import shutil
import subprocess

import structlog
from pydantic import BaseModel

from junior.config import Settings
from junior.runbook.base import Harness, LLMResult, Usage

logger = structlog.get_logger()

_TOOLS = "Read,Bash(git log:*,git show:*,git diff:*,git blame:*),Grep,Glob"


class ClaudeCodeHarness(Harness):
    name = "claudecode"
    file_access = True  # reads repo files via its own tools
    config_fields = ("model", "timeout")
    setup_note = "Uses the local `claude` CLI — run `claude` once to authenticate (no env var)."

    def is_ready(self) -> str:
        return "ready" if shutil.which("claude") else "not ready: `claude` CLI not found on PATH"

    def complete(
        self,
        *,
        system_prompt: str,
        user_message: str,
        output_schema: type[BaseModel],
        settings: Settings,
    ) -> LLMResult:
        project_dir = str(settings.context.project_dir)
        schema_json = json.dumps(output_schema.model_json_schema())

        logger.debug(
            "invoking claude CLI",
            model=settings.llm.model or None,
            schema=output_schema.__name__,
        )

        cmd = [
            "claude", "-p",
            "--output-format", "json",
            "--json-schema", schema_json,
            "--append-system-prompt", system_prompt,
            "--tools", _TOOLS,
            "--permission-mode", "bypassPermissions",
            "--no-session-persistence",
        ]
        if settings.llm.anthropic_api_key:
            cmd.append("--bare")
        if settings.llm.model:
            cmd.extend(["--model", settings.llm.model])

        try:
            proc = subprocess.run(
                cmd, input=user_message, capture_output=True, text=True,
                cwd=project_dir, timeout=settings.llm.timeout,
            )
        except FileNotFoundError:
            raise RuntimeError("claude CLI not found — install with: npm install -g @anthropic-ai/claude-code")
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"claude CLI timed out after {settings.llm.timeout}s (raise llm.timeout if expected)"
            )

        if proc.returncode != 0:
            if not proc.stdout.strip():
                raise RuntimeError(f"claude CLI failed (exit {proc.returncode}): {(proc.stderr or '')[-500:]}")
            logger.warning("claude CLI exited with non-zero code", returncode=proc.returncode, stderr=(proc.stderr or '')[-200:])

        raw = proc.stdout.strip()
        if not raw:
            raise RuntimeError(f"claude CLI returned empty output: {(proc.stderr or '')[-500:]}")

        messages = _parse_messages(raw)
        result_msg = _find_result(messages)
        if result_msg.get("is_error"):
            raise RuntimeError(f"claude CLI error: {result_msg.get('result', 'unknown error')}")

        output = _extract_output(messages, output_schema)
        input_t, output_t = _extract_token_usage(result_msg)
        return LLMResult(
            output=output,
            usage=Usage(input_tokens=input_t, output_tokens=output_t, total_tokens=input_t + output_t),
        )


HARNESS = ClaudeCodeHarness()


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


def _extract_output(messages: list[dict], output_schema: type[BaseModel]) -> BaseModel:
    """Extract the validated output from the StructuredOutput tool_use.

    With --json-schema, claude returns data via a StructuredOutput tool call as
    a dict in content[].input.
    """
    for msg in reversed(messages):
        if msg.get("type") != "assistant":
            continue
        for content in msg.get("message", {}).get("content", []):
            if content.get("type") == "tool_use" and content.get("name") == "StructuredOutput":
                return output_schema.model_validate(content["input"])

    raise RuntimeError("No StructuredOutput found in claude response")


def _extract_token_usage(result_msg: dict) -> tuple[int, int]:
    """Return (input, output) token counts. Cache tokens count as input."""
    usage = result_msg.get("usage", {})
    input_t = (
        usage.get("input_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
    )
    output_t = usage.get("output_tokens", 0)
    return input_t, output_t
