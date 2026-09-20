"""Pydantic AI engine.

A single structured call via the pydantic-ai SDK with file-exploration tools.
The model returns an instance of the requested output schema directly.
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel

from junior.config import Settings
from junior.runbook.base import EnvVar, Harness, LLMResult, Usage

if TYPE_CHECKING:
    from pydantic_ai import RunContext

_PROVIDER_KEY = EnvVar(
    "OPENAI_API_KEY / ANTHROPIC_API_KEY", True,
    "LLM provider key (matches your model's provider)",
)

logger = structlog.get_logger()


@dataclass
class ReviewDeps:
    project_dir: str
    max_file_size: int = 100_000


# --- File tools (available to the agent for exploring beyond the diff) ---

_SKIP_DIRS = frozenset({".git", "node_modules", ".venv", "venv", "__pycache__", ".tox", "dist", "build"})


def _safe_resolve(base_dir: str, user_path: str) -> Path:
    """Resolve user-provided path and ensure it stays within the project directory."""
    base = Path(base_dir).resolve()
    resolved = (base / user_path).resolve()
    if not resolved.is_relative_to(base):
        raise ValueError(f"Path traversal blocked: {user_path}")
    return resolved


def _read_file(ctx: RunContext[ReviewDeps], path: str) -> str:
    """Read a file from the project root.

    Args:
        path: File path relative to project root.
    """
    try:
        full_path = _safe_resolve(ctx.deps.project_dir, path)
    except ValueError:
        return f"Access denied: {path}"
    try:
        if full_path.stat().st_size > ctx.deps.max_file_size:
            return f"File too large (>{ctx.deps.max_file_size // 1024}KB): {path}"
        return full_path.read_text(encoding="utf-8", errors="ignore")
    except FileNotFoundError:
        return f"File not found: {path}"
    except OSError as e:
        return f"Error reading file: {e}"


def _list_dir(ctx: RunContext[ReviewDeps], path: str = ".") -> list[str]:
    """List files and directories at a path relative to project root.

    Args:
        path: Directory path relative to project root.
    """
    try:
        full_path = _safe_resolve(ctx.deps.project_dir, path)
    except ValueError:
        return [f"Access denied: {path}"]
    try:
        base = Path(ctx.deps.project_dir).resolve()
        return sorted(str(p.relative_to(base)) for p in full_path.iterdir())
    except OSError as e:
        return [f"Error listing directory: {e}"]


def _grep(ctx: RunContext[ReviewDeps], pattern: str, path: str = ".") -> list[str]:
    """Search for a regex pattern in source files.

    Args:
        pattern: Regex pattern to search for.
        path: File or directory path relative to project root (default: whole project).
    """
    try:
        full_path = _safe_resolve(ctx.deps.project_dir, path)
    except ValueError:
        return [f"Access denied: {path}"]
    try:
        regex = re.compile(pattern)
    except re.error:
        return [f"Invalid regex: {pattern}"]

    results: list[str] = []
    files = [full_path] if full_path.is_file() else [
        p for p in full_path.rglob("*")
        if not any(part in _SKIP_DIRS for part in p.parts)
    ]
    for f in files:
        if not f.is_file():
            continue
        try:
            for i, line in enumerate(
                f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
            ):
                if regex.search(line):
                    rel = str(f.relative_to(Path(ctx.deps.project_dir).resolve()))
                    results.append(f"{rel}:{i}: {line.strip()}")
                    if len(results) >= 50:
                        return results
        except OSError:
            continue
    return results


_TOOLS = [_read_file, _list_dir, _grep]


# --- Error translation (SDK exceptions → actionable messages) ---

# Provider phrasings for "the input exceeds the model's context window" (OpenAI
# and Anthropic word it differently; matched case-insensitively on HTTP 400).
_CONTEXT_OVERFLOW_MARKERS = (
    "context_length_exceeded",
    "maximum context length",
    "prompt is too long",
    "too many tokens",
    "exceeds the context window",
    "input tokens exceed",
)


def _provider_message(body: object) -> str:
    """Dig the human-readable message out of a provider error body.

    OpenAI nests it as ``{"error": {"message": ...}}``; Anthropic the same shape
    with an extra ``type`` — fall back to the raw body for anything else.
    """
    if isinstance(body, str):
        return body
    if isinstance(body, dict):
        err = body.get("error", body)
        if isinstance(err, dict) and isinstance(err.get("message"), str):
            return err["message"]
    return str(body) if body is not None else ""


def _translate_error(e: Exception, model_str: str) -> RuntimeError | None:
    """Map a pydantic-ai/provider exception to an actionable RuntimeError.

    Returns None for anything unrecognized — the caller re-raises the original
    so no stack trace information is lost.
    """
    from pydantic_ai.exceptions import ModelHTTPError, UsageLimitExceeded

    if isinstance(e, UsageLimitExceeded):
        return RuntimeError(
            f"response hit the configured output-token cap: {e}. "
            "Raise or unset llm.max_tokens_per_agent (MAX_TOKENS_PER_AGENT)."
        )
    if isinstance(e, ModelHTTPError):
        msg = _provider_message(e.body) or str(e)
        low = msg.lower()
        if e.status_code == 400 and any(m in low for m in _CONTEXT_OVERFLOW_MARKERS):
            return RuntimeError(
                f"input is too large for model '{model_str}': {msg} — shrink the input "
                "(lower context.max_diff_chars / llm.max_file_size, trim context files) "
                "or pick a model with a larger context window."
            )
        if e.status_code == 429:
            return RuntimeError(
                f"model '{model_str}' rate-limited the request (HTTP 429): {msg} — "
                "retry later or reduce concurrent junior runs."
            )
        if e.status_code in (401, 403):
            return RuntimeError(
                f"model '{model_str}' rejected the API key (HTTP {e.status_code}): {msg} — "
                "check OPENAI_API_KEY / ANTHROPIC_API_KEY."
            )
        return RuntimeError(f"model '{model_str}' call failed (HTTP {e.status_code}): {msg}")
    return None


class PydanticHarness(Harness):
    name = "pydantic"
    file_access = False  # gets the diff inline; tools are for extra exploration
    config_fields = ("max_tokens_per_agent",)
    env_vars = (_PROVIDER_KEY,)

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
        return asyncio.run(self._run(system_prompt, user_message, output_schema, settings))

    async def _run(
        self,
        system_prompt: str,
        user_message: str,
        output_schema: type[BaseModel],
        settings: Settings,
    ) -> LLMResult:
        from pydantic_ai import Agent, RunContext
        from pydantic_ai.usage import UsageLimits

        # The module-level file tools annotate their first parameter as
        # `RunContext[ReviewDeps]`, but pydantic_ai is imported lazily here (kept
        # off the module top level so `junior list` / registry scans don't pull
        # the SDK). `from __future__ import annotations` makes those annotations
        # strings that pydantic-ai resolves at runtime against the module globals
        # — so expose RunContext there before building the agent, otherwise tool
        # schema generation raises `NameError: name 'RunContext' is not defined`.
        globals()["RunContext"] = RunContext

        model_str = settings.llm.model_string
        deps = ReviewDeps(
            project_dir=str(settings.context.project_dir),
            max_file_size=settings.llm.max_file_size,
        )
        usage_limits = (
            UsageLimits(output_tokens_limit=settings.llm.max_tokens_per_agent)
            if settings.llm.max_tokens_per_agent
            else None
        )

        logger.debug("invoking pydantic-ai", model=model_str, schema=output_schema.__name__)

        agent = Agent(
            model_str,
            output_type=output_schema,
            deps_type=ReviewDeps,
            system_prompt=system_prompt,
            tools=_TOOLS,
        )
        try:
            result = await agent.run(user_message, deps=deps, usage_limits=usage_limits)
        except Exception as e:
            friendly = _translate_error(e, model_str)
            if friendly is not None:
                raise friendly from e
            raise
        u = result.usage
        input_t = u.input_tokens or 0
        output_t = u.output_tokens or 0
        return LLMResult(
            output=result.output,
            usage=Usage(input_tokens=input_t, output_tokens=output_t, total_tokens=input_t + output_t),
        )


HARNESS = PydanticHarness()
