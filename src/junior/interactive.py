"""Interactive prompts for Junior — used by both --init and --interactive run."""

from __future__ import annotations

import argparse
import os

import questionary

from junior.config import Settings


# --- Individual prompts --------------------------------------------------

def ask_backend(default: str | None = None) -> str | None:
    """Pick agent backend. Returns short name or None on cancel."""
    choices = [
        questionary.Choice("claudecode — uses local Claude CLI (no API key needed)", value="claudecode"),
        questionary.Choice("pydantic — parallel agents via OpenAI/Anthropic API", value="pydantic"),
        questionary.Choice("codex — uses local Codex CLI", value="codex"),
        questionary.Choice("deepagents — LangChain orchestrator + subagents", value="deepagents"),
    ]
    return questionary.select(
        "Backend (which AI runs the review):",
        choices=choices,
        default=_match_default(choices, default),
    ).ask()


def ask_provider(default: str | None = None) -> str | None:
    """Pick LLM provider (only relevant for pydantic / deepagents)."""
    choices = [
        questionary.Choice("openai — uses OPENAI_API_KEY", value="openai"),
        questionary.Choice("anthropic — uses ANTHROPIC_API_KEY", value="anthropic"),
    ]
    return questionary.select(
        "Provider:",
        choices=choices,
        default=_match_default(choices, default),
    ).ask()


def ask_model(default: str | None, backend: str) -> str | None:
    """Pick model name. Returns the entered string (empty allowed for codex/auto)."""
    hint = {
        "pydantic": "e.g. gpt-5.4-mini, claude-sonnet-4-6",
        "deepagents": "e.g. gpt-5.4-mini, claude-sonnet-4-6",
        "claudecode": "leave empty to let the CLI choose",
        "codex": "ignored — codex CLI picks its own model",
    }.get(backend, "")
    return questionary.text(
        f"Model name ({hint}):" if hint else "Model name:",
        default=default or "",
    ).ask()


def ask_source(default: str | None = None) -> str | None:
    """Pick source mode."""
    choices = [
        questionary.Choice("auto — smart detection (CI base, branch diff, or uncommitted)", value="auto"),
        questionary.Choice("staged — staged changes only (git diff --cached)", value="staged"),
        questionary.Choice("commit — last commit (git diff HEAD~1)", value="commit"),
        questionary.Choice("branch — current branch vs target branch", value="branch"),
    ]
    return questionary.select(
        "Source (what to review):",
        choices=choices,
        default=_match_default(choices, default),
    ).ask()


def ask_target_branch(default: str = "main") -> str | None:
    """Target branch for the branch diff."""
    return questionary.text(
        "Target branch (for diff comparison):",
        default=default,
    ).ask()


def ask_prompts_text(default: str = "security,logic,design") -> str | None:
    """Free-text prompts (used by --init, stored as comma-separated string)."""
    return questionary.text(
        "Prompts to run (comma-separated):",
        default=default,
    ).ask()


def ask_prompts_select(default: list[str], available: list[str]) -> list[str] | None:
    """Multi-select prompts from the available set (used by --interactive)."""
    if not available:
        return list(default)
    choices = [
        questionary.Choice(name, value=name, checked=name in default)
        for name in available
    ]
    selected = questionary.checkbox(
        "Prompts to run (space to toggle, enter to accept):",
        choices=choices,
    ).ask()
    if selected is None:
        return None
    if not selected:
        questionary.print("At least one prompt is required; keeping previous selection.")
        return list(default)
    return selected


def ask_output_mode(default: str = "stdout") -> str | None:
    """Pick where to publish the review."""
    choices = [
        questionary.Choice("stdout — print to console", value="stdout"),
        questionary.Choice("file — write to a markdown file", value="file"),
        questionary.Choice("publish — post to GitLab MR / GitHub PR", value="publish"),
    ]
    return questionary.select(
        "Output target:",
        choices=choices,
        default=_match_default(choices, default),
    ).ask()


def ask_output_file(default: str = "review.md") -> str | None:
    """Filename to write the review into."""
    return questionary.text(
        "Output file path:",
        default=default,
    ).ask()


def confirm_run(summary: str) -> bool:
    """Show summary and ask to proceed."""
    questionary.print(summary)
    answer = questionary.confirm("Run now?", default=True).ask()
    return bool(answer)


# --- Orchestrator ---------------------------------------------------------

def interactive_run(
    settings: Settings,
    args: argparse.Namespace,
    available_prompts: list[str],
) -> tuple[Settings, argparse.Namespace] | None:
    """Walk the user through every relevant flag, then return updated state.

    Defaults come from the already-loaded Settings + args. None on cancel.
    """
    questionary.print("Junior — interactive run")
    questionary.print("(Press Enter to accept the default shown in [brackets]. Ctrl+C cancels.)\n")

    overrides: dict = {}

    # Backend
    backend = ask_backend(default=settings.agent_backend.name.lower())
    if backend is None:
        return None
    overrides["agent_backend"] = backend

    # Provider — only when backend uses an external LLM API
    needs_provider = backend in ("pydantic", "deepagents")
    if needs_provider:
        provider = ask_provider(default=settings.model_provider or "openai")
        if provider is None:
            return None
        overrides["model_provider"] = provider
    else:
        overrides["model_provider"] = ""

    # Model name
    model = ask_model(default=settings.model_name, backend=backend)
    if model is None:
        return None
    overrides["model_name"] = model.strip()

    # Source mode
    source = ask_source(default=settings.source)
    if source is None:
        return None
    overrides["source"] = source

    # Target branch — only meaningful for branch / auto comparisons
    target_branch = ask_target_branch(
        default=settings.ci_merge_request_target_branch_name or "main",
    )
    if target_branch is None:
        return None
    overrides["ci_merge_request_target_branch_name"] = target_branch.strip() or "main"

    # Prompts
    current_prompts = [
        p.strip() for p in (args.prompts or settings.prompts).split(",") if p.strip()
    ]
    prompts = ask_prompts_select(default=current_prompts, available=available_prompts)
    if prompts is None:
        return None
    overrides["prompts"] = ",".join(prompts)
    args.prompts = overrides["prompts"]

    # Output mode
    default_mode = _current_output_mode(args, settings)
    mode = ask_output_mode(default=default_mode)
    if mode is None:
        return None

    args.publish = None
    args.output_file = None
    overrides["publish_output"] = ""
    if mode == "file":
        file_default = args.output_file or settings.publish_output or "review.md"
        path = ask_output_file(default=file_default)
        if path is None:
            return None
        args.output_file = path
        overrides["publish_output"] = path
    elif mode == "publish":
        args.publish = "__auto__"

    new_settings = Settings(**{**settings.model_dump(), **overrides})

    summary = _format_summary(new_settings, args, mode)
    if not confirm_run(summary):
        questionary.print("Cancelled.")
        return None

    return new_settings, args


# --- Helpers --------------------------------------------------------------

def _match_default(choices: list[questionary.Choice], value: str | None) -> questionary.Choice | None:
    """questionary.select needs the Choice object matching a value, not the raw value."""
    if value is None:
        return None
    for choice in choices:
        if choice.value == value:
            return choice
    return None


def _current_output_mode(args: argparse.Namespace, settings: Settings) -> str:
    if getattr(args, "publish", None):
        return "publish"
    if args.output_file or settings.publish_output:
        return "file"
    return "stdout"


def _format_summary(settings: Settings, args: argparse.Namespace, mode: str) -> str:
    lines = [
        "",
        "Ready to run with:",
        f"  Backend  : {settings.agent_backend.name.lower()}",
    ]
    if settings.model_provider:
        lines.append(f"  Provider : {settings.model_provider}")
    if settings.display_model:
        lines.append(f"  Model    : {settings.display_model}")
    lines.append(f"  Source   : {settings.source} vs {settings.ci_merge_request_target_branch_name}")
    lines.append(f"  Prompts  : {settings.prompts}")

    if mode == "publish":
        platform = settings.resolved_publisher.name.lower()
        lines.append(f"  Output   : publish to {platform}")
    elif mode == "file":
        lines.append(f"  Output   : {args.output_file}")
    else:
        lines.append("  Output   : stdout")

    if settings.agent_backend.name.lower() in ("pydantic", "deepagents"):
        env_var = (
            "OPENAI_API_KEY" if settings.model_provider == "openai" else "ANTHROPIC_API_KEY"
        )
        if not os.environ.get(env_var):
            lines.append(f"  Warning  : {env_var} is not set in your environment.")

    return "\n".join(lines)
