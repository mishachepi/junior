"""Interactive wizard for Junior — used by both `init` and `run -i`.

The individual `ask_*` prompts live in `interactive.prompts`. This module
defines the `InteractiveIO` state DTO and the `interactive_run` orchestrator
that composes the prompts into the full wizard.

The `ask_*` and `confirm_run` callables are re-imported here so that
`monkeypatch.setattr(interactive, "ask_harness", ...)` in tests rebinds the
exact name `interactive_run` looks up — keeping the wizard testable without
having to know the internal module layout.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

import questionary

from junior.config import Settings
from junior.interactive.prompts import (
    ask_config_target,
    ask_harness,
    ask_model,
    ask_output_file,
    ask_output_mode,
    ask_runbook,
    ask_publish,
    ask_source,
    ask_target_branch,
    confirm_run,
)


__all__ = [
    "InteractiveIO",
    "interactive_run",
    "ask_config_target",
    "ask_harness",
    "ask_model",
    "ask_output_file",
    "ask_output_mode",
    "ask_runbook",
    "ask_publish",
    "ask_source",
    "ask_target_branch",
    "confirm_run",
]


@dataclass(frozen=True)
class InteractiveIO:
    """Mutable wizard state shared between the CLI and `interactive_run`.

    Holds only the bits the wizard reads or writes — runbook-level Settings
    are passed separately. Prompts (`--prompt` / `--prompt-file`) are not in
    here because the wizard does not modify them: pass via CLI or config.
    """

    output_file: Path | None
    publish_enabled: bool


def interactive_run(
    settings: Settings,
    io: InteractiveIO,
) -> tuple[Settings, InteractiveIO] | None:
    """Walk the user through every relevant flag, then return updated state.

    Defaults come from `settings` + `io`. Returns None on user cancel.
    """
    questionary.print("Junior — interactive run")
    questionary.print("(Press Enter to accept the default shown in [brackets]. Ctrl+C cancels.)\n")

    llm_over: dict = {}
    context_over: dict = {}
    output_over: dict = {}

    from junior.runbook.registry import available_runbooks, load_local_runbooks

    if settings.local_runbooks:
        load_local_runbooks(settings.context.project_dir)
    runbook = ask_runbook(available_runbooks(), default=settings.runbook)
    if runbook is None:
        return None

    harness = ask_harness(default=settings.llm.harness_name)
    if harness is None:
        return None
    llm_over["harness"] = harness

    model = ask_model(default=settings.llm.model, harness=harness)
    if model is None:
        return None
    llm_over["model"] = model.strip()

    source = ask_source(default=settings.context.source.value)
    if source is None:
        return None
    context_over["source"] = source

    target_branch = ask_target_branch(default=settings.context.target_branch or "main")
    if target_branch is None:
        return None
    context_over["target_branch"] = target_branch.strip() or "main"

    default_mode = _current_output_mode(io)
    mode = ask_output_mode(default=default_mode)
    if mode is None:
        return None

    # Snapshot the existing file path before we rewrite it, so "file" mode
    # defaults to whatever -o was given (or what's already in settings).
    previous_file = str(io.output_file) if io.output_file else (
        settings.output.output_file or "review.md"
    )

    new_output_file: Path | None = None
    new_publish_enabled = False
    output_over["output_file"] = ""

    if mode == "file":
        path = ask_output_file(default=previous_file)
        if path is None:
            return None
        new_output_file = Path(path)
        output_over["output_file"] = path
    elif mode == "publish":
        new_publish_enabled = True
        output_over["publish"] = True

    base = settings.model_dump()
    base["runbook"] = runbook
    base.setdefault("llm", {}).update(llm_over)
    base.setdefault("context", {}).update(context_over)
    base.setdefault("output", {}).update(output_over)
    new_settings = Settings(**base)

    new_io = replace(
        io,
        output_file=new_output_file,
        publish_enabled=new_publish_enabled,
    )

    summary = _format_summary(new_settings, new_io, mode)
    if not confirm_run(summary):
        questionary.print("Cancelled.")
        return None

    return new_settings, new_io


def _current_output_mode(io: InteractiveIO) -> str:
    if io.publish_enabled:
        return "publish"
    if io.output_file:
        return "file"
    return "stdout"


def _format_summary(settings: Settings, io: InteractiveIO, mode: str) -> str:
    harness = settings.llm.harness_name
    lines = [
        "",
        "Ready to run with:",
        f"  Runbook  : {settings.runbook}",
        f"  Harness  : {harness}",
    ]
    if settings.llm.display_model:
        lines.append(f"  Model    : {settings.llm.display_model}")
    lines.append(
        f"  Source   : {settings.context.source.value} vs {settings.context.target_branch}"
    )
    prompt_count = len(settings.context.prompts)
    lines.append(f"  Prompts  : {prompt_count} (set via --prompt / --prompt-file / config)")

    if mode == "publish":
        lines.append(f"  Output   : publish via {settings.runbook}")
    elif mode == "file":
        lines.append(f"  Output   : {io.output_file}")
    else:
        lines.append("  Output   : stdout")

    if harness in ("pydantic", "deepagents"):
        provider = settings.llm.resolved_provider
        if provider:
            env_var = f"{provider.upper()}_API_KEY"
            if not os.environ.get(env_var):
                lines.append(f"  Warning  : {env_var} is not set in your environment.")
        else:
            lines.append(
                "  Warning  : no provider resolved — set OPENAI_API_KEY / ANTHROPIC_API_KEY "
                "or pass --model anthropic:..."
            )

    return "\n".join(lines)
