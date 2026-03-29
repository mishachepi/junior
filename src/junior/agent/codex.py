"""Codex CLI implementation of code review agent.

Single subprocess call to `codex exec` — no tool loops, predictable cost.
Codex has its own file tools and sandbox, so we just pass the prompt.
"""

import json
import os
import re
import subprocess
import tempfile

import structlog

from junior.config import Settings
from junior.models import (
    CollectedContext,
    ReviewResult,
)
from junior.agent.core import build_review_prompt, build_user_message
from junior.prompt_loader import Prompt

logger = structlog.get_logger()

_OUTPUT_SCHEMA = ReviewResult.model_json_schema()


def _ensure_codex_auth(settings: Settings) -> None:
    """Ensure codex CLI is authenticated. Uses existing OAuth or OPENAI_API_KEY."""
    # Check if already logged in
    try:
        result = subprocess.run(
            ["codex", "login", "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            logger.debug("codex already authenticated")
            return
    except (FileNotFoundError, subprocess.TimeoutExpired):
        raise RuntimeError("codex CLI not found — install with: npm install -g @openai/codex")

    # Not logged in — try API key
    api_key = settings.openai_api_key
    if not api_key:
        raise RuntimeError(
            "codex is not authenticated. Either run 'codex login' or set OPENAI_API_KEY."
        )

    try:
        result = subprocess.run(
            ["codex", "login", "--with-api-key"],
            input=api_key,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            logger.info("codex authenticated via OPENAI_API_KEY")
        else:
            raise RuntimeError(f"codex login failed: {result.stderr[:300]}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("codex login timed out")


def review(context: CollectedContext, settings: Settings, prompts: list[Prompt]) -> ReviewResult:
    """Run AI review via codex exec subprocess."""
    _ensure_codex_auth(settings)
    prompt = _build_prompt(context, settings, prompts)

    logger.info(
        "invoking codex CLI review",
        prompts=[p.name for p in prompts],
        changed_files=len(context.changed_files),
        prompt_size=len(prompt),
    )

    # Write output schema to temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as schema_f:
        json.dump(_OUTPUT_SCHEMA, schema_f)
        schema_path = schema_f.name

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as output_f:
        output_path = output_f.name

    try:
        cmd = [
            "codex",
            "exec",
            "--output-schema",
            schema_path,
            "-o",
            output_path,
            "-C",
            settings.ci_project_dir,
            "--ephemeral",
            "--skip-git-repo-check",
            prompt,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
            )
        except FileNotFoundError:
            raise RuntimeError("codex CLI not found — install with: npm install -g @openai/codex")
        except subprocess.TimeoutExpired:
            raise RuntimeError("codex CLI timed out after 10 minutes")

        if result.returncode != 0:
            logger.error(
                "codex exec failed",
                returncode=result.returncode,
                stderr=result.stderr[-2000:],
                stdout=result.stdout[-500:] if result.stdout else None,
            )
            raise RuntimeError(
                f"codex exec failed (exit {result.returncode}): {result.stderr[-2000:]}"
            )

        # Read the last message output
        try:
            with open(output_path) as f:
                raw_output = f.read().strip()
        except OSError as e:
            raise RuntimeError(f"Failed to read codex output file: {e}")

        if not raw_output:
            raise RuntimeError("codex returned empty output")

        review_result = _parse_response(raw_output)
        review_result.tokens_used = _parse_token_usage(result.stderr)
        return review_result
    finally:
        os.unlink(schema_path)
        os.unlink(output_path)


def _parse_response(output: str) -> ReviewResult:
    """Parse codex CLI output into ReviewResult with validation."""
    text = output.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline >= 0:
            text = text[first_newline + 1 :]
        else:
            text = text[3:]  # just strip the fence marker
    if text.endswith("```"):
        text = text[:-3].rstrip()

    # Extract JSON from possible surrounding text
    json_start = text.find("{")
    json_end = text.rfind("}") + 1
    if json_start >= 0 and json_end > json_start:
        text = text[json_start:json_end]

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error("codex output is not valid JSON", output=text[:500], error=str(e))
        raise RuntimeError(f"Failed to parse codex output as JSON: {e}")

    try:
        return ReviewResult.model_validate(data)
    except Exception as e:
        logger.error("codex output failed validation", data=data, error=str(e))
        raise RuntimeError(f"Codex output failed ReviewResult validation: {e}")


def _parse_token_usage(stderr: str) -> int:
    """Extract token count from codex stderr (last line: 'N,NNN')."""
    # codex prints "tokens used\nN,NNN" at the end of stderr
    match = re.search(r"(\d[\d,]+)\s*$", stderr.strip())
    if match:
        return int(match.group(1).replace(",", ""))
    return 0


def _build_prompt(context: CollectedContext, settings: Settings, prompts: list[Prompt]) -> str:
    """Build a compact prompt for codex — instructions + metadata, no full diff."""
    parts = [
        build_review_prompt(prompts, settings.ci_project_dir),
        "---\n",
        build_user_message(context, include_diff=False),
    ]
    return "\n".join(parts)
