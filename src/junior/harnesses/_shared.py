"""Shared base for the CLI-driven harnesses (claudecode, codex, pi, agy).

Every one of them is a single `subprocess.run` of a local agent CLI with the
same failure modes (binary missing, timeout) and — for CLIs without a native
output-schema flag — the same trick: append the JSON Schema to the prompt and
validate the reply ourselves. `CliHarness` holds the run; `schema_contract` and
`parse_json_reply` hold the schema-in-prompt contract.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import ClassVar

import structlog
from pydantic import BaseModel

from junior.config import LLMSettings
from junior.runbook.base import Harness

logger = structlog.get_logger()


class CliHarness(Harness):
    """A harness that drives one local CLI in one subprocess call."""

    #: executable looked up on PATH (also names the CLI in error messages)
    binary: ClassVar[str]
    #: how to install it, shown when the binary is missing
    install_hint: ClassVar[str]

    def is_ready(self) -> str:
        if shutil.which(self.binary):
            return "ready"
        return f"not ready: `{self.binary}` CLI not found on PATH"

    def run_cli(
        self,
        cmd: list[str],
        llm: LLMSettings,
        *,
        input: str | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """`subprocess.run` with the two failures every CLI shares turned into
        the RuntimeError the runner reports. Exit codes are the caller's to
        judge — some CLIs return non-zero and still print a usable reply."""
        try:
            return subprocess.run(
                cmd, input=input, capture_output=True, text=True,
                cwd=cwd, env=env, timeout=llm.timeout, check=False,
            )
        except FileNotFoundError:
            raise RuntimeError(
                f"{self.binary} CLI not found — install with: {self.install_hint}"
            ) from None
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"{self.binary} CLI timed out after {llm.timeout}s "
                "(raise llm.timeout if expected)"
            ) from None


_OUTPUT_CONTRACT = (
    "## Output format\n"
    "When you are done, reply with ONLY one JSON object — no prose, no markdown "
    "fences — that validates against this JSON Schema:\n"
)


def schema_contract(output_schema: type[BaseModel]) -> str:
    """Prompt suffix for CLIs without a native schema flag (pi): the
    JSON Schema the reply must validate against — `parse_json_reply` checks it."""
    return f"{_OUTPUT_CONTRACT}{json.dumps(output_schema.model_json_schema())}"


def parse_json_reply(text: str, output_schema: type[BaseModel], *, source: str) -> BaseModel:
    """Extract the outermost JSON object from `text` and validate it.

    Tolerant by design: drops ```fences``` and any prose around the object.
    `source` names the harness in log/error messages (e.g. "codex", "pi").
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.find("\n")
        cleaned = cleaned[first_newline + 1 :] if first_newline >= 0 else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].rstrip()

    json_start = cleaned.find("{")
    json_end = cleaned.rfind("}") + 1
    if json_start >= 0 and json_end > json_start:
        cleaned = cleaned[json_start:json_end]

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error(f"{source} output is not valid JSON", output=cleaned[:500], error=str(e))
        raise RuntimeError(f"Failed to parse {source} output as JSON: {e}")

    try:
        return output_schema.model_validate(data)
    except Exception as e:
        logger.error(f"{source} output failed validation", data=data, error=str(e))
        raise RuntimeError(f"{source} output failed {output_schema.__name__} validation: {e}")
