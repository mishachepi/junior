"""Build frozen Settings from config + CLI overrides; preflight + log."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import structlog
import typer
from pydantic import ValidationError

from junior.config import (
    Settings,
    SourceMode,
    _deep_merge,
    find_global_config,
    find_local_config,
    load_configs,
)

from junior.cli.console import err_console, error
from junior.cli.observability import log_startup, setup_logging
from junior.cli.options import parse_kv


@dataclass(frozen=True)
class GlobalOpts:
    """Options on the parent command — apply to every subcommand."""

    config: Optional[str] = None  # path, or "-" for stdin
    verbose: bool = False


def used_config_files(globals_: GlobalOpts) -> list[Path]:
    """Return concrete config files that contributed to settings (for logs)."""
    paths: list[Path] = []
    g = find_global_config()
    if g:
        paths.append(g)
    local = find_local_config()
    if local:
        paths.append(local)
    if globals_.config and globals_.config != "-":
        paths.append(Path(globals_.config))
    return paths


def build_settings(
    *,
    config: Optional[str] = None,
    harness: Optional[str] = None,
    model: Optional[str] = None,
    source: Optional[SourceMode] = None,
    base_sha: Optional[str] = None,
    project_dir: Optional[Path] = None,
    target_branch: Optional[str] = None,
    prompts: Optional[list[str]] = None,
    prompt_files: Optional[list[str]] = None,
    context: Optional[dict[str, str]] = None,
    context_files: Optional[dict[str, str]] = None,
    input_text: Optional[str] = None,
    output_file: Optional[Path] = None,
    publish: Optional[bool] = None,
    no_record: bool = False,
    runbook: Optional[str] = None,
) -> Settings:
    """Merge config files + CLI overrides into a frozen Settings. Exits on error.

    All fields are optional; pass only what the subcommand actually has.

    Scalar *configuration* flags are aliases for `--env KEY=VALUE`: they're
    exported into the process environment and reach Settings through the normal
    env channel — one precedence story (env > config file) and free inheritance
    by harness subprocesses and script-runbook commands. They run after
    `apply_env`, so an explicit flag wins over its own `--env` pair.

    Two flags are NOT env aliases, on purpose:
    - `--runbook` / `--harness` are primary selectors — they choose what THIS
      process runs and stay process-local init args. Exporting RUNBOOK would
      leak into any nested `junior run` (e.g. inside a script-runbook command)
      and loop it back into the parent's runbook.
    - Additive flags (--prompt / --context / --context-file) stay merge layers:
      a single env var can't express "append to what the config already has".
    """
    flag_env: dict[str, Optional[str]] = {
        "MODEL": model or None,
        "SOURCE": source.value if source is not None else None,
        "BASE_SHA": base_sha or None,
        "PROJECT_DIR": str(project_dir) if project_dir else None,
        "TARGET_BRANCH": target_branch or None,
        # tri-state: --publish / --no-publish; absent = leave env/config alone
        "PUBLISH": None if publish is None else ("true" if publish else "false"),
        "RECORD": "false" if no_record else None,
    }
    if output_file is not None:
        # `-o -` means "force stdout": an empty OUTPUT_FILE still shadows a
        # config-file `output_file`, so the override works.
        of = str(output_file)
        flag_env["OUTPUT_FILE"] = "" if of == "-" else of
    for name, value in flag_env.items():
        if value is not None:
            os.environ[name] = value

    try:
        file_config = load_configs(override_path=config)
    except ValueError as e:
        error(str(e))
        raise typer.Exit(code=2)

    cli_kwargs: dict[str, dict] = {"context": {}, "llm": {}}
    if harness:
        cli_kwargs["llm"]["harness"] = harness
    if context:
        cli_kwargs["context"]["context"] = context
    if context_files:
        cli_kwargs["context"]["context_files"] = context_files
    if input_text:
        # Task data (the positional argument), not configuration — stays an
        # init layer rather than an env export (can be large and multiline).
        cli_kwargs["context"]["input_text"] = input_text
    cli_kwargs = {k: v for k, v in cli_kwargs.items() if v}
    if runbook:
        cli_kwargs["runbook"] = runbook

    merged = _deep_merge(file_config, cli_kwargs)

    # CLI --prompt / --prompt-file *append* to config prompts. --prompt-file
    # paths are resolved against CWD and converted to absolute file:// URIs
    # so downstream loaders don't need to know they came from a flag.
    cli_entries: list[str] = list(prompts or [])
    for raw in prompt_files or []:
        cli_entries.append(f"file://{Path(raw).resolve()}")
    if cli_entries:
        ctx = merged.setdefault("context", {})
        ctx["prompts"] = list(ctx.get("prompts") or []) + cli_entries

    try:
        return Settings(**merged)
    except ValidationError as e:
        for err in e.errors():
            # pydantic prefixes custom-validator messages with "Value error, "
            error(str(err["msg"]).removeprefix("Value error, "))
        raise typer.Exit(code=2)


def apply_env(pairs: Optional[list[str]]) -> None:
    """Apply `--env KEY=VALUE` pairs to the process environment.

    Must run before Settings are built: the vars then carry normal env
    precedence (explicit CLI flags still win) and are inherited by harness
    subprocesses and script-runbook collect/publish commands.
    """
    if not pairs:
        return
    for key, value in parse_kv(pairs, "--env").items():
        if not key:
            raise typer.BadParameter(f"empty KEY in --env '={value}', expected KEY=VALUE")
        os.environ[key] = value


def prepare_settings(
    globals_: GlobalOpts,
    *,
    verbose: bool = False,
    env: Optional[list[str]] = None,
    **build_kwargs,
) -> tuple[Settings, "structlog.BoundLogger"]:
    """Build settings, set up logging, return (settings, logger). Exits on error.

    `verbose` is the per-subcommand `-v` flag; it's OR'd with the parent `-v` so
    `junior -v dry-run` and `junior dry-run -v` both enable debug logging.
    `env` is the `--env KEY=VALUE` list, applied to os.environ before the build.
    """
    apply_env(env)
    settings = build_settings(config=globals_.config, **build_kwargs)
    debug = globals_.verbose or verbose
    setup_logging("DEBUG" if debug else settings.log_level.value)
    return settings, structlog.get_logger()


def _check_project_dir(settings: Settings) -> list[str]:
    """Fail fast for obvious file-system errors before we shell out to git.

    Without this, an absent directory or non-git path produces a cascade
    of seven cryptic 'git command error' warnings before junior gives up.
    """
    path = settings.context.project_dir
    if not path.exists():
        return [f"project directory does not exist: {path}"]
    if not path.is_dir():
        return [f"project path is not a directory: {path}"]
    if not (path / ".git").exists():
        return [f"not a git repository (no .git found): {path}"]
    return []


def log_and_preflight(
    logger,
    settings: Settings,
    globals_: GlobalOpts,
    *,
    publish_enabled: bool,
    prompts: list,
    review_check: bool,
    publish_check: bool,
    check_project_dir: bool = True,
    runbook=None,
) -> None:
    """Emit startup log, run preflight, exit on config errors.

    Generic checks come from `settings.preflight`; publish/platform checks are
    runbook-specific and come from `runbook.validate` when a runbook is given.
    """
    config_files = used_config_files(globals_)
    log_startup(
        logger, settings,
        publish_enabled=publish_enabled,
        prompts=prompts,
        config_files=config_files,
    )

    # Setup errors = genuine config/environment problems (`junior config init`
    # can help). Runbook errors = capability problems (e.g. this runbook can't
    # publish) — their own message is already actionable, so no init hint.
    setup_errors: list[str] = []
    # Explicit input text replaces the git diff as the review subject, so a
    # git repo is not required for that run.
    git_required = (
        runbook is None or getattr(runbook, "needs_git", True)
    ) and not settings.context.input_text
    if check_project_dir and git_required:
        setup_errors.extend(_check_project_dir(settings))
    setup_errors.extend(settings.preflight(review=review_check))

    runbook_errors = (
        runbook.validate(settings, publish_enabled=publish_check) if runbook is not None else []
    )

    if setup_errors or runbook_errors:
        for err in (*setup_errors, *runbook_errors):
            error(str(err))
        if setup_errors and (review_check or publish_check):
            err_console.print("\n[dim]Hint: run 'junior config init' for interactive setup.[/]")
        raise typer.Exit(code=2)
