"""Reusable Typer option/argument types and small CLI parsers.

These are the building blocks for subcommand signatures — they're declared
once here and reused across `run` and `dry-run` so each subcommand's
signature stays short and consistent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from junior import __version__
from junior.config import SourceMode


# === Rich help panels ===

CTX_PANEL = "Context — what to review"
REVIEW_PANEL = "Review — how to review"
OUTPUT_PANEL = "Output — where to send"
OPS_PANEL = "Operational"


# Per-subcommand verbose, so `-v` works after the command too (the parent
# callback also defines `-v`; whichever is given wins via an OR in prepare_settings).
VerboseOpt = Annotated[
    bool,
    typer.Option(
        "-v",
        "--verbose",
        help="Enable debug logging",
        rich_help_panel=OPS_PANEL,
    ),
]

# Runbooks and harnesses declare the env vars they need (`junior config env`
# lists them); --env supplies any of those inline instead of exporting first.
EnvOpt = Annotated[
    Optional[list[str]],
    typer.Option(
        "--env",
        metavar="KEY=VALUE",
        help=(
            "Set an env var for this run (repeatable) — same precedence as exported "
            "env vars. Visible to settings, the harness subprocess, and script-runbook "
            "commands. `junior config env` lists what the harness+runbook need."
        ),
        rich_help_panel=OPS_PANEL,
        show_default=False,
    ),
]


# The same --config as the parent callback, repeated on flag-heavy subcommands
# so it works *after* the command too (`junior run --config x.yaml`), not only
# before it. There is still one effective config: the post-command value wins
# when both positions are given (see app.run / dry_run).
ConfigOpt = Annotated[
    Optional[str],
    typer.Option(
        "--config",
        metavar="FILE",
        help="YAML config file ('-' = stdin). Same flag as before the subcommand; "
        "overrides .junior.{yaml,yml} + global config.",
        rich_help_panel=OPS_PANEL,
        show_default=False,
    ),
]


# === Small parsers / callbacks ===


def parse_kv(values: Optional[list[str]], flag_name: str) -> dict[str, str]:
    """Parse a list of KEY=VALUE strings into a dict."""
    if not values:
        return {}
    out: dict[str, str] = {}
    for v in values:
        if "=" not in v:
            raise typer.BadParameter(
                f"invalid {flag_name} format '{v}', expected KEY=VALUE"
            )
        key, _, value = v.partition("=")
        out[key.strip()] = value.strip()
    return out


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"junior {__version__}")
        raise typer.Exit()


# === Reusable Annotated option types (shared across subcommands) ===

ProjectDirArg = Annotated[
    Optional[Path],
    typer.Argument(
        metavar="[PROJECT_DIR]",
        help="Path to git repository (default: current directory)",
        show_default=False,
        rich_help_panel=CTX_PANEL,
    ),
]

# `junior run` / `dry-run` take free text positionally; the project dir moved
# to --project-dir so the positional slot always means "task input".
InputArg = Annotated[
    Optional[str],
    typer.Argument(
        metavar="[INPUT]",
        help=(
            "The subject to act on — the content itself, not instructions about "
            "it. code_review reviews THIS text instead of a git diff; a script "
            "runbook uses it as the user message. For instructions use --prompt."
        ),
        show_default=False,
        rich_help_panel=CTX_PANEL,
    ),
]

ProjectDirOpt = Annotated[
    Optional[Path],
    typer.Option(
        "--project-dir",
        metavar="PATH",
        help="Path to git repository (default: current directory). Alias for --env PROJECT_DIR=…",
        show_default=False,
        rich_help_panel=CTX_PANEL,
    ),
]

SourceOpt = Annotated[
    Optional[SourceMode],
    typer.Option(
        "--source",
        help="What to review: auto, staged, commit, branch. Alias for --env SOURCE=…",
        rich_help_panel=CTX_PANEL,
        show_default=False,
        case_sensitive=False,
    ),
]

BaseShaOpt = Annotated[
    Optional[str],
    typer.Option(
        "--base-sha",
        metavar="SHA",
        help="Diff against this commit. Wins over CI auto-vars. Alias for --env BASE_SHA=…",
        rich_help_panel=CTX_PANEL,
        show_default=False,
    ),
]

TargetBranchOpt = Annotated[
    Optional[str],
    typer.Option(
        "--target-branch",
        help="Target branch for diff. Alias for --env TARGET_BRANCH=… "
        "(CI auto-var: CI_MERGE_REQUEST_TARGET_BRANCH_NAME)",
        rich_help_panel=CTX_PANEL,
        show_default=False,
    ),
]

ContextInstructionOpt = Annotated[
    Optional[list[str]],
    typer.Option(
        "--context",
        metavar='KEY="text"',
        help='Named background fact folded into the prompt as "KEY: text" '
        '(e.g. ticket="JIRA-12 …"). Repeatable. Data, not instructions — '
        "for instructions use --prompt.",
        rich_help_panel=CTX_PANEL,
        show_default=False,
    ),
]

ContextFileOpt = Annotated[
    Optional[list[str]],
    typer.Option(
        "--context-file",
        metavar="KEY=path",
        help="Named data file folded into the prompt as KEY — like --context, "
        "but the value is read from a file. Repeatable.",
        rich_help_panel=CTX_PANEL,
        show_default=False,
    ),
]

PromptOpt = Annotated[
    Optional[list[str]],
    typer.Option(
        "--prompt",
        metavar="TEXT",
        help="Instructions for the LLM — what to do / what to focus on. "
        "Repeatable. (Background facts → --context; the thing to act on → "
        "the [INPUT] argument.)",
        rich_help_panel=CTX_PANEL,
        show_default=False,
    ),
]

PromptFileOpt = Annotated[
    Optional[list[Path]],
    typer.Option(
        "--prompt-file",
        metavar="FILE",
        help="Instructions from a .md file — like --prompt, read from a file. "
        "Repeatable.",
        rich_help_panel=CTX_PANEL,
        show_default=False,
    ),
]

HarnessOpt = Annotated[
    Optional[str],
    typer.Option(
        "--harness",
        "--backend",  # deprecated alias, kept for one version
        help="LLM harness: claudecode, pydantic, codex, deepagents, pi. "
        "env: HARNESS (--backend/BACKEND deprecated)",
        rich_help_panel=REVIEW_PANEL,
        show_default=False,
    ),
]

ModelOpt = Annotated[
    Optional[str],
    typer.Option(
        "--model",
        help=(
            "Model spec: 'provider:model' (e.g. anthropic:claude-opus-4-6) "
            "or bare 'model' (provider auto-detected from API key). "
            "Alias for --env MODEL=…"
        ),
        rich_help_panel=REVIEW_PANEL,
        show_default=False,
    ),
]

RunbookOpt = Annotated[
    Optional[str],
    typer.Option(
        "--runbook",
        help=(
            "Runbook (module) to run: local_review, github_pr_review, "
            "gitlab_pr_review, bitbucket_pr_review, or 'pkg.module:ClassName'. "
            "env: RUNBOOK"
        ),
        rich_help_panel=REVIEW_PANEL,
        show_default=False,
    ),
]

OutputFileOpt = Annotated[
    Optional[Path],
    typer.Option(
        "-o",
        "--output-file",
        help="Write review to file instead of stdout. '-' forces stdout (overrides "
        "config output_file). Alias for --env OUTPUT_FILE=…",
        rich_help_panel=OUTPUT_PANEL,
        show_default=False,
    ),
]

PublishOpt = Annotated[
    Optional[bool],
    typer.Option(
        "--publish/--no-publish",
        help=(
            "Run the runbook's custom publish (post to platform / pretty render). "
            "Without it you get the raw output on stdout/-o. Overrides config: "
            "--publish forces on, --no-publish forces off. Alias for --env PUBLISH=true|false."
        ),
        rich_help_panel=OUTPUT_PANEL,
        show_default=False,
    ),
]

PublishFileOpt = Annotated[
    Optional[Path],
    typer.Option(
        "--publish-file",
        metavar="REVIEW_FILE",
        help="Skip runbook; publish this pre-generated .md to the platform",
        rich_help_panel=OUTPUT_PANEL,
        show_default=False,
    ),
]

NoRecordOpt = Annotated[
    bool,
    typer.Option(
        "--no-record",
        help="Don't write the .junior/output/{timestamp}.json run record (on by "
        "default). Alias for --env RECORD=false",
        rich_help_panel=OUTPUT_PANEL,
    ),
]

FromFileOpt = Annotated[
    Optional[Path],
    typer.Option(
        "--from-file",
        metavar="CONTEXT_FILE",
        help=(
            "Load CollectedContext from JSON, skip phase 1. "
            "Symmetric with `junior dry-run -o ctx.json`"
        ),
        rich_help_panel=CTX_PANEL,
        show_default=False,
    ),
]

InteractiveOpt = Annotated[
    bool,
    typer.Option(
        "-i",
        "--interactive",
        help="Interactive run — confirm/override every flag before launching",
        rich_help_panel=OPS_PANEL,
    ),
]
