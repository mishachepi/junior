"""Gemini CLI engine (https://geminicli.com — Google's `gemini`).

Single subprocess call to `gemini --output-format json` — the agent may use its
(read-only) file tools, then answers with one text reply we parse as JSON.
Gemini's CLI has no native output-schema flag, so the contract is enforced from
our side (like `pi`): the JSON Schema is appended to the prompt and the reply is
parsed + validated against the requested model.

Read-only by construction: `--approval-mode plan` lets the CLI read the repo
with its built-in tools but never edit/run anything — a review must not mutate
the worktree. `--skip-trust` is required so headless runs don't silently
downgrade that mode in an untrusted directory.

The run is kept hermetic: the whole prompt arrives on stdin (no ARG_MAX limit on
large diffs), and Junior's runbook supplies every instruction.
"""

import json
import shutil
import subprocess

import structlog
from pydantic import BaseModel

from junior.config import Settings
from junior.harnesses._shared import parse_json_reply
from junior.runbook.base import EnvVar, Harness, LLMResult, Usage

logger = structlog.get_logger()

_OUTPUT_CONTRACT = (
    "## Output format\n"
    "When you are done, reply with ONLY one JSON object — no prose, no markdown "
    "fences — that validates against this JSON Schema:\n"
)


class GeminiHarness(Harness):
    name = "gemini"
    file_access = True  # reads repo files via its own (plan-mode, read-only) tools
    config_fields = ("model", "timeout")
    env_vars = (
        EnvVar(
            "GEMINI_API_KEY",
            False,
            "Google API key for the chosen model (gemini also accepts its own "
            "logged-in auth / Vertex env — local key not required if already set up)",
        ),
    )
    setup_note = (
        "Uses the local `gemini` CLI — set GEMINI_API_KEY or authenticate it once "
        "(`gemini`); reviews run read-only (--approval-mode plan)."
    )

    def is_ready(self) -> str:
        return "ready" if shutil.which("gemini") else "not ready: `gemini` CLI not found on PATH"

    def complete(
        self,
        *,
        system_prompt: str,
        user_message: str,
        output_schema: type[BaseModel],
        settings: Settings,
    ) -> LLMResult:
        schema_json = json.dumps(output_schema.model_json_schema())
        prompt = f"{system_prompt}\n\n{_OUTPUT_CONTRACT}{schema_json}\n\n---\n\n{user_message}"

        logger.debug(
            "invoking gemini CLI",
            model=settings.llm.model or "(gemini default)",
            schema=output_schema.__name__,
        )

        cmd = [
            "gemini",
            "--output-format", "json",
            "--approval-mode", "plan",  # read-only: read repo, never edit/run
            "--skip-trust",  # headless: keep plan mode instead of downgrading
        ]
        if settings.llm.model:
            cmd.extend(["--model", settings.llm.model])

        try:
            proc = subprocess.run(
                cmd, input=prompt, capture_output=True, text=True,
                cwd=str(settings.context.project_dir), timeout=settings.llm.timeout,
            )
        except FileNotFoundError:
            raise RuntimeError(
                "gemini CLI not found — install with: npm install -g @google/gemini-cli"
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"gemini CLI timed out after {settings.llm.timeout}s (raise llm.timeout if expected)"
            )

        text, usage = _parse_envelope(proc.stdout, proc.returncode, proc.stderr)
        output = parse_json_reply(text, output_schema, source="gemini")
        return LLMResult(output=output, usage=usage)


HARNESS = GeminiHarness()


# --- Output parsing ---


def _parse_envelope(stdout: str, returncode: int, stderr: str) -> tuple[str, Usage]:
    """Pull the model's text + token usage out of `gemini --output-format json`.

    The envelope is a single object: ``{response, stats, error?}``. We surface a
    CLI `error` (or a non-zero exit with no usable response) as a RuntimeError so
    the runner reports it like every other harness failure.
    """
    raw = (stdout or "").strip()
    if not raw:
        raise RuntimeError(
            f"gemini CLI returned empty output (exit {returncode}): {(stderr or '')[-500:]}"
        )

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"gemini output is not valid JSON (exit {returncode}): {e}")

    error = data.get("error") if isinstance(data, dict) else None
    response = data.get("response") if isinstance(data, dict) else None
    if not response:
        detail = _error_detail(error) or (stderr or "")[-500:]
        raise RuntimeError(f"gemini returned no response (exit {returncode}): {detail}")

    return response, _sum_tokens(data.get("stats"))


def _error_detail(error: object) -> str:
    """Human-readable text from the envelope's optional `error` object."""
    if isinstance(error, dict):
        return str(error.get("message") or error)
    return str(error) if error else ""


def _sum_tokens(stats: object) -> Usage:
    """Sum per-model token usage from the envelope's `stats.models` map.

    Gemini bills `prompt` tokens inclusive of cached ones, so input is `prompt`
    as-is (no double count); `candidates` is the output. Best-effort: a missing
    or differently-shaped stats block yields zeros, never an error.
    """
    input_t = output_t = total_t = 0
    models = stats.get("models") if isinstance(stats, dict) else None
    for entry in (models or {}).values():
        tokens = entry.get("tokens") if isinstance(entry, dict) else None
        if not isinstance(tokens, dict):
            continue
        input_t += int(tokens.get("prompt") or 0)
        output_t += int(tokens.get("candidates") or 0)
        total_t += int(tokens.get("total") or 0)
    return Usage(
        input_tokens=input_t,
        output_tokens=output_t,
        total_tokens=total_t or input_t + output_t,
    )
