"""Pydantic AI implementation of code review agent.

Specialist sub-agents run in parallel (one per prompt),
then findings are merged into a single ReviewResult.
"""

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

import structlog
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.usage import UsageLimits

from junior.config import Settings
from junior.models import (
    CollectedContext,
    ReviewComment,
    ReviewResult,
    determine_recommendation,
)
from junior.agent.core import build_review_prompt, build_user_message
from junior.prompt_loader import Prompt

logger = structlog.get_logger()


@dataclass
class ReviewDeps:
    project_dir: str
    max_file_size: int = 100_000


class SubAgentFindings(BaseModel):
    """Findings from a single specialist sub-agent."""

    comments: list[ReviewComment] = Field(default_factory=list)


_SUMMARY_PROMPT = """You are a senior code reviewer. Given findings from specialists,
write a concise 2-3 sentence summary of the overall code quality.
Be direct, constructive, and actionable. If there are no findings, say the code looks good."""


# --- File tools (shared across all sub-agents) ---

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

# TODO: maybe switch to https://github.com/vstorm-co/pydantic-ai-backend or something like that
_TOOLS = [_read_file, _list_dir, _grep]


# --- Entry point ---


def review(context: CollectedContext, settings: Settings, prompts: list[Prompt]) -> ReviewResult:
    """Run AI review using Pydantic AI. Returns structured ReviewResult."""
    return asyncio.run(_review_async(context, settings, prompts))


async def _review_async(
    context: CollectedContext,
    settings: Settings,
    prompts: list[Prompt],
) -> ReviewResult:
    model_str = settings.model_string
    deps = ReviewDeps(project_dir=settings.ci_project_dir, max_file_size=settings.max_file_size)
    user_msg = build_user_message(context)
    usage_limits = (
        UsageLimits(response_tokens_limit=settings.max_tokens_per_agent)
        if settings.max_tokens_per_agent
        else None
    )

    logger.info(
        "invoking pydantic-ai review",
        model=model_str,
        prompts=[p.name for p in prompts],
        changed_files=len(context.changed_files),
    )

    # Create one agent per prompt, run in parallel
    # build_review_prompt adds BASE_RULES + project instructions (AGENT.md/CLAUDE.md)
    agents = [
        Agent(
            model_str,
            output_type=SubAgentFindings,
            deps_type=ReviewDeps,
            system_prompt=build_review_prompt([p], settings.ci_project_dir),
            tools=_TOOLS,
        )
        for p in prompts
    ]

    # Limit concurrency to avoid API rate limits (env: MAX_CONCURRENT_AGENTS)
    semaphore = asyncio.Semaphore(settings.max_concurrent_agents)

    async def _run_with_limit(agent):
        async with semaphore:
            return await agent.run(user_msg, deps=deps, usage_limits=usage_limits)

    raw_results = await asyncio.gather(
        *(_run_with_limit(agent) for agent in agents),
        return_exceptions=True,
    )

    all_comments: list[ReviewComment] = []
    review_errors: list[str] = []
    total_tokens = 0
    for i, r in enumerate(raw_results):
        if isinstance(r, Exception):
            error_msg = f"Agent '{prompts[i].name}' failed: {r}"
            logger.error("sub-agent failed", prompt=prompts[i].name, error=str(r))
            review_errors.append(error_msg)
            continue
        all_comments.extend(r.output.comments)
        total_tokens += r.usage().total_tokens or 0

    if len(review_errors) == len(prompts):
        raise RuntimeError(f"All {len(prompts)} sub-agents failed")

    # Generate summary
    summary_agent: Agent[None, str] = Agent(
        model_str,
        output_type=str,
        system_prompt=_SUMMARY_PROMPT,
    )
    findings_text = (
        "\n".join(f"- [{c.severity.value}] [{c.category.value}] {c.message}" for c in all_comments)
        or "No issues found."
    )
    summary_result = await summary_agent.run(f"Findings:\n{findings_text}")
    total_tokens += summary_result.usage().total_tokens or 0

    return ReviewResult(
        summary=summary_result.output,
        recommendation=determine_recommendation(all_comments),
        comments=all_comments,
        tokens_used=total_tokens,
        review_errors=review_errors,
    )
