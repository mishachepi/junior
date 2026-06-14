"""Pi coding agent CLI engine (https://pi.dev / badlogic/pi-mono).

Single subprocess call to `pi --mode json` — the agent may use its (read-only)
file tools, then must answer with one JSON object. Pi has no native output-schema
flag, so the schema contract is enforced from our side: the JSON Schema is
appended to the system prompt and the reply is parsed + validated against the
requested model.

Why pi: it is provider-agnostic with first-class **local models** — point
`~/.pi/agent/models.json` at any OpenAI/Anthropic-compatible endpoint (Ollama,
LM Studio, vLLM) and select it with `junior --harness pi --model provider/id`.
Cloud providers work too (env key or `~/.pi/agent/auth.json`).

The run is kept hermetic: no session persistence, no user extensions / skills /
prompt templates / context files — Junior's runbook supplies the whole prompt.
"""

import json
import os
import shutil
import subprocess

import structlog
from pydantic import BaseModel

from junior.config import Settings
from junior.harnesses._shared import parse_json_reply
from junior.runbook.base import EnvVar, Harness, LLMResult, Usage

logger = structlog.get_logger()

#: read-only file tools; no bash/edit/write — review must not mutate the repo.
_TOOLS = "read,grep,find,ls"

_OUTPUT_CONTRACT = (
    "## Output format\n"
    "When you are done, reply with ONLY one JSON object — no prose, no markdown "
    "fences — that validates against this JSON Schema:\n"
)


class PiHarness(Harness):
    name = "pi"
    file_access = True  # reads repo files via its own read/grep/find/ls tools
    config_fields = ("model",)
    env_vars = (
        EnvVar(
            "ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY / …",
            False,
            "provider key for the chosen model (pi also reads ~/.pi/agent/auth.json; "
            "local models need none — configure ~/.pi/agent/models.json)",
        ),
    )
    setup_note = (
        "Uses the local `pi` CLI — add local models via ~/.pi/agent/models.json "
        "(Ollama/LM Studio/vLLM) or authenticate a provider once."
    )

    def is_ready(self) -> str:
        return "ready" if shutil.which("pi") else "not ready: `pi` CLI not found on PATH"

    def complete(
        self,
        *,
        system_prompt: str,
        user_message: str,
        output_schema: type[BaseModel],
        settings: Settings,
    ) -> LLMResult:
        schema_json = json.dumps(output_schema.model_json_schema())
        full_system = f"{system_prompt}\n\n{_OUTPUT_CONTRACT}{schema_json}"

        logger.debug(
            "invoking pi CLI",
            model=settings.llm.model or "(pi default)",
            schema=output_schema.__name__,
        )

        cmd = [
            "pi", "--mode", "json",
            "--no-session",
            "--no-extensions", "--no-skills", "--no-prompt-templates", "--no-context-files",
            "--tools", _TOOLS,
            "--system-prompt", full_system,
        ]
        if settings.llm.model:
            cmd.extend(["--model", settings.llm.model])
        cmd.append(user_message)  # the positional message goes last

        env = dict(os.environ)
        env["PI_OFFLINE"] = "1"  # no startup update checks/telemetry

        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                cwd=str(settings.context.project_dir), env=env, timeout=600,
            )
        except FileNotFoundError:
            raise RuntimeError(
                "pi CLI not found — install with: npm install -g @mariozechner/pi"
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("pi CLI timed out after 10 minutes")

        text, usage = _last_assistant(proc.stdout)
        if proc.returncode != 0 and not text:
            raise RuntimeError(
                f"pi CLI failed (exit {proc.returncode}): {(proc.stderr or '')[-1000:]}"
            )
        if not text:
            raise RuntimeError(
                f"pi returned no assistant message: {(proc.stderr or '')[-500:]}"
            )

        output = _parse_response(text, output_schema)
        return LLMResult(output=output, usage=usage)


HARNESS = PiHarness()


# --- Output parsing ---


def _last_assistant(stdout: str) -> tuple[str, Usage]:
    """Final assistant text + summed token usage from pi's JSON event lines.

    Each `message_end` with role=assistant carries that turn's text content and
    its own `usage` {input, output, cacheRead, cacheWrite}. The answer is the
    last turn's text; usage sums every turn (tool loops bill each round-trip).
    """
    text = ""
    input_t = output_t = 0
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "message_end":
            continue
        message = event.get("message") or {}
        if message.get("role") != "assistant":
            continue
        parts = [
            block.get("text", "")
            for block in message.get("content") or []
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        if any(p.strip() for p in parts):
            text = "\n".join(p for p in parts if p)
        usage = message.get("usage") or {}
        input_t += (
            int(usage.get("input") or 0)
            + int(usage.get("cacheRead") or 0)
            + int(usage.get("cacheWrite") or 0)
        )
        output_t += int(usage.get("output") or 0)
    return text, Usage(
        input_tokens=input_t, output_tokens=output_t, total_tokens=input_t + output_t
    )


def _parse_response(text: str, output_schema: type[BaseModel]) -> BaseModel:
    """Parse the assistant's reply into an instance of `output_schema`."""
    return parse_json_reply(text, output_schema, source="pi")
