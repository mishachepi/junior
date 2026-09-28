"""Antigravity CLI engine (https://antigravity.google/docs/cli — Google's `agy`).

Single headless subprocess call to `agy --print … --output-format json
--json-schema …`. The agent may read the repository with its own tools, then
the CLI enforces the requested schema itself and hands back the validated
object in the envelope's `structured_output` — native structured output, like
claudecode; no schema-in-prompt contract needed.

The whole prompt (system_prompt + user_message) travels as the `--print`
argument: agy has no system-prompt flag and does not read a prompt from stdin.
Argument size is bounded by the OS (ARG_MAX: 1 MiB on macOS, 2 MiB on Linux),
which the runbooks' `max_diff_chars` cap (200k) keeps clear of.

Permissions are agy's own (`~/.gemini/antigravity-cli/settings.json`): in
headless mode it can't prompt, so anything not allowed there — shell commands
and file writes, by default — is auto-denied with `status: SUCCESS`, an empty
`response` and a `denied_actions` list. The harness turns that into a
RuntimeError naming the denied action, so a run that produced nothing never
looks like a model answer.

`file_access = False` on purpose: the "diff dropped, read it with your tools"
path of the code-review runbook needs `git` — a shell command agy denies
headlessly — so the diff is always inlined (like pydantic). agy still reads
repository files on its own for context beyond the diff.
"""

import json

import structlog
from pydantic import BaseModel

from junior.config import Settings
from junior.harnesses._shared import CliHarness, parse_json_reply
from junior.runbook.base import LLMResult, Usage

logger = structlog.get_logger()

# Headless agy denies shell commands; without this note the model's first move
# on a review is `git …` / `ls`, which is soft-denied and ends the turn empty.
_HEADLESS_NOTE = (
    "Environment note: this is a headless session without a shell — do not run "
    "commands. Read files with your file tools if you need more context, then answer."
)


class AgyHarness(CliHarness):
    name = "agy"
    binary = "agy"
    install_hint = "brew install --cask antigravity-cli  (https://antigravity.google/docs/cli)"
    file_access = False  # diff inlined: fetching it itself would need shell (denied headlessly)
    config_fields = ("model", "timeout")
    setup_note = (
        "Uses the local `agy` CLI — run `agy` once to log in (no env var); "
        "headless runs reuse the cached credentials."
    )

    def complete(
        self,
        *,
        system_prompt: str,
        user_message: str,
        output_schema: type[BaseModel],
        settings: Settings,
    ) -> LLMResult:
        prompt = f"{system_prompt}\n\n{_HEADLESS_NOTE}\n\n---\n\n{user_message}"
        schema_json = json.dumps(output_schema.model_json_schema())

        logger.debug(
            "invoking agy CLI",
            model=settings.llm.model or "(agy default)",
            schema=output_schema.__name__,
        )

        # `--print=<prompt>`: the `=` form keeps a prompt that starts with `-`
        # (or any following flag) from being eaten by Go's flag parser.
        cmd = [
            "agy",
            f"--print={prompt}",
            "--output-format", "json",
            "--json-schema", schema_json,
        ]
        if settings.llm.model:
            cmd.extend(["--model", settings.llm.model])

        proc = self.run_cli(cmd, settings, cwd=str(settings.context.project_dir))

        data = _parse_envelope(proc.stdout, proc.returncode, proc.stderr)
        output = _extract_output(data, output_schema)
        return LLMResult(output=output, usage=_usage(data.get("usage")))


HARNESS = AgyHarness()


# --- Output parsing ---


def _parse_envelope(stdout: str, returncode: int, stderr: str) -> dict:
    """Decode `agy --output-format json` and fail on anything but a successful turn.

    The envelope is one object: ``{status, response, error?, usage,
    structured_output?, denied_actions?}``. A non-SUCCESS status or an `error`
    surfaces as RuntimeError so the runner reports it like every other harness.
    """
    raw = (stdout or "").strip()
    if not raw:
        raise RuntimeError(
            f"agy CLI returned empty output (exit {returncode}): {(stderr or '')[-500:]}"
        )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"agy output is not valid JSON (exit {returncode}): {e}")
    if not isinstance(data, dict):
        # every harness failure is a RuntimeError — the runner maps it to exit 3
        raise RuntimeError(f"Unexpected agy output type: {type(data).__name__}")  # noqa: TRY004

    status = data.get("status")
    error = data.get("error")
    if error or (status and status != "SUCCESS"):
        detail = _error_detail(error) or (stderr or "")[-500:]
        raise RuntimeError(f"agy CLI failed (status {status}, exit {returncode}): {detail}")
    return data


def _extract_output(data: dict, output_schema: type[BaseModel]) -> BaseModel:
    """Validated output: `structured_output` first, the text reply as a fallback.

    With `--json-schema` agy validates the answer and embeds it as
    `structured_output`. If that field is missing we parse the text `response`
    (fences stripped, outermost object extracted). An empty response almost
    always means a headless auto-deny — say which action was denied.
    """
    structured = data.get("structured_output")
    if isinstance(structured, dict):
        return output_schema.model_validate(structured)

    response = data.get("response")
    if response and response.strip():
        return parse_json_reply(response, output_schema, source="agy")

    denied = [
        str(d.get("display_name") or d.get("action") or d)
        for d in (data.get("denied_actions") or [])
        if d
    ]
    if denied:
        raise RuntimeError(
            "agy produced no answer — headless mode auto-denied: "
            f"{', '.join(denied)}. Allow it under permissions.allow in "
            "~/.gemini/antigravity-cli/settings.json, or keep the runbook read-only."
        )
    raise RuntimeError("agy returned no response and no structured_output")


def _error_detail(error: object) -> str:
    """Human-readable text from the envelope's optional `error` field."""
    if isinstance(error, dict):
        return str(error.get("message") or error)
    return str(error) if error else ""


def _usage(usage: object) -> Usage:
    """Token counts from the envelope's `usage` block (best-effort, never raises).

    agy reports `output_tokens` inclusive of `thinking_tokens` and `total_tokens`
    = input + output, so the three map straight onto `Usage`.
    """
    if not isinstance(usage, dict):
        return Usage()
    input_t = int(usage.get("input_tokens") or 0)
    output_t = int(usage.get("output_tokens") or 0)
    total_t = int(usage.get("total_tokens") or 0)
    return Usage(
        input_tokens=input_t,
        output_tokens=output_t,
        total_tokens=total_t or input_t + output_t,
    )
