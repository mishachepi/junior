"""Codex CLI engine.

Single subprocess call to `codex exec` — no tool loops, predictable cost.
Codex has its own file tools and sandbox for context beyond the inlined diff
(the code-review runbook drops the diff from the message only when oversized);
the engine drives the CLI with a strict output schema built from the requested
result model.
"""

import json
import os
import re
import tempfile
from pathlib import Path

import structlog
from pydantic import BaseModel

from junior.config import LLMSettings
from junior.harnesses._shared import CliHarness, parse_json_reply, stderr_tail
from junior.runbook.base import LLMResult, Usage

logger = structlog.get_logger()


def _build_output_schema(output_schema: type[BaseModel]) -> dict:
    """Build a strict JSON schema suitable for codex CLI structured output."""
    from openai.lib._pydantic import to_strict_json_schema

    return to_strict_json_schema(output_schema)


class CodexHarness(CliHarness):
    name = "codex"
    binary = "codex"
    install_hint = "npm install -g @openai/codex"
    file_access = True  # reads repo files via its own sandbox
    config_fields = ("model", "timeout")
    setup_note = "Uses the local `codex` CLI — authenticate it once (no env var)."

    def _ensure_auth(self, llm: LLMSettings) -> None:
        """Use codex's existing login, else log in with OPENAI_API_KEY."""
        if self.run_cli([self.binary, "login", "status"], llm, timeout=10).returncode == 0:
            logger.debug("codex already authenticated")
            return
        if not llm.openai_api_key:
            raise RuntimeError(
                "codex is not authenticated. Either run 'codex login' or set OPENAI_API_KEY."
            )
        proc = self.run_cli(
            [self.binary, "login", "--with-api-key"], llm, input=llm.openai_api_key, timeout=15
        )
        if proc.returncode != 0:
            raise RuntimeError(f"codex login failed: {stderr_tail(proc, 300)}")
        logger.info("codex authenticated via OPENAI_API_KEY")

    def complete(
        self,
        *,
        system_prompt: str,
        user_message: str,
        output_schema: type[BaseModel],
        llm: LLMSettings,
        project_dir: Path,
    ) -> LLMResult:
        self._ensure_auth(llm)
        prompt = f"{system_prompt}\n---\n\n{user_message}"

        logger.debug("invoking codex CLI", schema=output_schema.__name__, prompt_size=len(prompt))

        schema_path = output_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as schema_f:
                # Capture the path before json.dump so a failing schema build
                # (e.g. missing `openai`) still gets cleaned up in `finally`.
                schema_path = schema_f.name
                json.dump(_build_output_schema(output_schema), schema_f)
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as output_f:
                output_path = output_f.name

            cmd = [
                self.binary, "exec",
                "--output-schema", schema_path,
                "-o", output_path,
                "-C", str(project_dir),
                "--ephemeral",
                "--skip-git-repo-check",
                prompt,
            ]

            result = self.run_cli(cmd, llm)

            if result.returncode != 0:
                logger.error(
                    "codex exec failed",
                    returncode=result.returncode,
                    stderr=stderr_tail(result, 2000),
                    stdout=result.stdout[-500:] if result.stdout else None,
                )
                raise RuntimeError(
                    f"codex exec failed (exit {result.returncode}): {stderr_tail(result, 2000)}"
                )

            try:
                with open(output_path) as f:
                    raw_output = f.read().strip()
            except OSError as e:
                raise RuntimeError(f"Failed to read codex output file: {e}")

            if not raw_output:
                raise RuntimeError("codex returned empty output")

            output = parse_json_reply(raw_output, output_schema, source="codex")
            total = _parse_token_usage(result.stderr)
            return LLMResult(output=output, usage=Usage(total_tokens=total))
        finally:
            if schema_path:
                os.unlink(schema_path)
            if output_path:
                os.unlink(output_path)


HARNESS = CodexHarness()


def _parse_token_usage(stderr: str) -> int:
    """Extract token count from codex stderr."""
    lines = [line.strip() for line in stderr.splitlines()]
    for index in range(len(lines) - 2, -1, -1):
        if lines[index].lower() != "tokens used":
            continue
        token_line = lines[index + 1]
        if re.fullmatch(r"\d[\d,]*", token_line):
            return int(token_line.replace(",", ""))
        logger.warning("codex token usage marker found without a valid count", value=token_line)
        return 0

    logger.debug("codex token usage marker not found")
    return 0
