"""Typer app, callback, and subcommand definitions.

The command bodies here are thin orchestration — they parse flags, build
Settings, log+preflight, and delegate the actual work to functions in
`junior.cli.actions`. Reusable option types live in `junior.cli.options`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from junior.cli.actions import (
    emit_output,
    load_or_collect_context,
    load_prompts,
    preview_run,
    publish_pre_generated,
    resolve_harness,
    resolve_runbook,
    run_interactive,
    run_review,
    save_context,
)
from junior.cli.config_show import print_example_config
from junior.cli.options import (
    BaseShaOpt,
    ConfigOpt,
    ContextFileOpt,
    ContextInstructionOpt,
    EnvOpt,
    FromFileOpt,
    HarnessOpt,
    InteractiveOpt,
    ModelOpt,
    NoRecordOpt,
    OPS_PANEL,
    OUTPUT_PANEL,
    OutputFileOpt,
    RunbookOpt,
    InputArg,
    ProjectDirArg,
    ProjectDirOpt,
    PromptFileOpt,
    PromptOpt,
    PublishFileOpt,
    PublishOpt,
    SourceOpt,
    TargetBranchOpt,
    VerboseOpt,
    parse_kv,
    version_callback,
)
from junior.cli.settings_builder import (
    GlobalOpts,
    build_settings,
    log_and_preflight,
    prepare_settings,
)
from junior.config import find_global_config, find_local_config
from junior.interactive import InteractiveIO


app = typer.Typer(
    name="junior",
    help="Junior — hand any task to an AI junior: deterministic runbooks, one schema-validated LLM call.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    add_completion=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

config_app = typer.Typer(
    help="Configure Junior — create (init), list extensions (list), inspect YAML defaults (show), env (env), or file locations (path).",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
app.add_typer(config_app, name="config")


@app.callback()
def _callback(
    ctx: typer.Context,
    config: Annotated[
        Optional[str],
        typer.Option(
            "--config",
            metavar="FILE",
            help=(
                "YAML config file. Use '-' to read YAML from stdin. "
                "Overrides .junior.{yaml,yml} and the global config."
            ),
            rich_help_panel=OPS_PANEL,
            show_default=False,
        ),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option(
            "-v",
            "--verbose",
            help="Enable debug logging",
            rich_help_panel=OPS_PANEL,
        ),
    ] = False,
    _version: Annotated[
        Optional[bool],
        typer.Option(
            "--version",
            help="Show version and exit",
            is_eager=True,
            callback=version_callback,
            rich_help_panel=OPS_PANEL,
        ),
    ] = None,
) -> None:
    """Junior — hand any task to an AI junior.

    A runbook collects context, one schema-validated LLM call does the task,
    the result is published deterministically. Built-in code review for
    GitLab / GitHub / Bitbucket DC — or any runbook you write.

    Common flows:

    \b
      junior run                Run your configured runbook
      junior run --publish      Run + publish (post to the PR/MR, pretty render, …)
      junior dry-run            Preview the run (context + prompts + plan), no AI
      junior dry-run -o ctx.json    Save phase-1 context to disk
      junior run --from-file ctx.json   Re-run phase 2 on saved context
      junior runs last          Print the newest run record (audit trail)
      junior config list        List available runbooks + harnesses (alias: junior list)
      junior config init        Interactive setup wizard (alias: junior init)
      junior config show        Print a YAML config skeleton
    """
    ctx.obj = GlobalOpts(config=config, verbose=verbose)


def _resolve_globals(ctx: typer.Context, config: Optional[str]) -> GlobalOpts:
    """Merge a post-command `--config` with the parent (global-position) one.

    There is one effective config: the value nearest the command wins, so
    `junior run --config x` works and `junior --config a run --config b` uses b.
    """
    globals_: GlobalOpts = ctx.obj or GlobalOpts()
    if config:
        return GlobalOpts(config=config, verbose=globals_.verbose)
    return globals_


@app.command()
def run(
    ctx: typer.Context,
    input_text: InputArg = None,
    project_dir: ProjectDirOpt = None,
    source: SourceOpt = None,
    base_sha: BaseShaOpt = None,
    target_branch: TargetBranchOpt = None,
    prompt: PromptOpt = None,
    prompt_file: PromptFileOpt = None,
    extra_context: ContextInstructionOpt = None,
    context_files: ContextFileOpt = None,
    from_file: FromFileOpt = None,
    harness: HarnessOpt = None,
    model: ModelOpt = None,
    runbook_name: RunbookOpt = None,
    output_file: OutputFileOpt = None,
    publish: PublishOpt = None,
    publish_file: PublishFileOpt = None,
    no_record: NoRecordOpt = False,
    interactive: InteractiveOpt = False,
    env: EnvOpt = None,
    config: ConfigOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """Run the selected runbook end-to-end: collect → AI review (harness) → publish.

    Pick the runbook with --runbook (or RUNBOOK / config `runbook:` — required,
    no implicit default) and the LLM driver with --harness (default claudecode).
    Each run writes a JSON record to .junior/output/ unless --no-record is set.

    Exit codes: 0=success, 1=blocking issues, 2=config error, 3=runtime error.
    """
    if input_text and (from_file or publish_file):
        # Both replace the collect step — silently dropping the explicit
        # positional INPUT would be unpredictable, so refuse the combination.
        raise typer.BadParameter(
            "positional INPUT conflicts with --from-file/--publish-file — "
            "they already supply the run's input; drop one of them",
            param_hint="[INPUT]",
        )

    globals_ = _resolve_globals(ctx, config)
    settings, logger = prepare_settings(
        globals_,
        verbose=verbose,
        env=env,
        harness=harness,
        model=model,
        runbook=runbook_name,
        publish=publish,
        no_record=no_record,
        source=source,
        base_sha=base_sha,
        project_dir=project_dir,
        target_branch=target_branch,
        prompts=prompt,
        prompt_files=[str(p) for p in prompt_file] if prompt_file else None,
        # `prompt_files` is just CLI sugar — settings_builder converts each
        # path to a `file://...` URI and appends to `context.prompts`.
        context=parse_kv(extra_context, "--context"),
        context_files=parse_kv(context_files, "--context-file"),
        input_text=input_text,
        output_file=output_file,
    )

    if interactive:
        settings, new_io = run_interactive(
            settings,
            InteractiveIO(
                output_file=output_file,
                publish_enabled=settings.output.publish,
            ),
        )
        output_file = new_io.output_file

    publish_enabled = settings.output.publish  # from --publish / config / interactive
    runbook = resolve_runbook(settings)

    needs_review = publish_file is None
    loaded_prompts = load_prompts(settings, logger) if needs_review else []

    # `--from-file` and `--publish-file` skip collection entirely, so the
    # project_dir doesn't need to be a git repo (or even exist).
    needs_local_git = publish_file is None and from_file is None
    log_and_preflight(
        logger, settings, globals_,
        publish_enabled=publish_enabled or publish_file is not None,
        prompts=loaded_prompts,
        review_check=needs_review,
        publish_check=publish_enabled or publish_file is not None,
        check_project_dir=needs_local_git,
        runbook=runbook,
    )

    if publish_file:
        publish_pre_generated(settings, publish_file, runbook, logger)
        return

    harness = resolve_harness(settings)
    context_data = load_or_collect_context(runbook, settings, from_file, logger)
    if runbook.is_empty(context_data):
        logger.info("no changes found, nothing to review")
        return

    result = run_review(
        runbook, harness, context_data, settings,
        publish_enabled=publish_enabled, logger=logger,
    )
    # No --publish → emit the raw result to stdout/-o. With --publish the
    # runbook handles output itself: local_review renders Markdown to stdout
    # (redirect with `>` to save it), platform runbooks post to the PR/MR.
    if not publish_enabled:
        emit_output(runbook, settings, result.output, logger)
    blocking = runbook.is_blocking(result.output)

    logger.info(
        "done",
        runbook=runbook.name,
        harness=settings.llm.harness_name,
        tokens=result.usage.total_tokens or None,
        output=runbook.output_destination(settings, publish_enabled=publish_enabled),
        blocking=blocking or None,
        **runbook.summary(result.output),
    )
    if blocking:
        raise typer.Exit(code=1)


@app.command(name="dry-run")
def dry_run(
    ctx: typer.Context,
    input_text: InputArg = None,
    project_dir: ProjectDirOpt = None,
    source: SourceOpt = None,
    base_sha: BaseShaOpt = None,
    target_branch: TargetBranchOpt = None,
    prompt: PromptOpt = None,
    prompt_file: PromptFileOpt = None,
    extra_context: ContextInstructionOpt = None,
    context_files: ContextFileOpt = None,
    harness: HarnessOpt = None,
    model: ModelOpt = None,
    runbook_name: RunbookOpt = None,
    publish: PublishOpt = None,
    output_file: Annotated[
        Optional[Path],
        typer.Option(
            "-o",
            "--output-file",
            metavar="CTX.json",
            help="Also save the collected context as JSON (replay with run --from-file)",
            rich_help_panel=OUTPUT_PANEL,
            show_default=False,
        ),
    ] = None,
    env: EnvOpt = None,
    config: ConfigOpt = None,
    verbose: VerboseOpt = False,
) -> None:
    """Preview a run without calling the AI — the plan + exactly what the harness gets.

    Prints the plan (runbook, harness + params, output schema, publish flag),
    the collected context, and the exact system prompt + user message the harness
    would receive. Mirrors `junior run` flags; pass `-o ctx.json` to also save the
    context for `run --from-file` (split collect from review, e.g. for CI).
    """
    if output_file is not None and str(output_file) == "-":
        # `-o -` (force stdout) is a `run` convention; dry-run's -o saves the
        # context JSON, which would collide with the preview on stdout.
        raise typer.BadParameter(
            "dry-run saves the context to a file; '-' (stdout) is not supported here",
            param_hint="-o",
        )

    globals_ = _resolve_globals(ctx, config)
    settings, logger = prepare_settings(
        globals_,
        verbose=verbose,
        env=env,
        harness=harness,
        model=model,
        runbook=runbook_name,
        publish=publish,
        source=source,
        base_sha=base_sha,
        project_dir=project_dir,
        target_branch=target_branch,
        prompts=prompt,
        prompt_files=[str(p) for p in prompt_file] if prompt_file else None,
        context=parse_kv(extra_context, "--context"),
        context_files=parse_kv(context_files, "--context-file"),
        input_text=input_text,
        output_file=output_file,
    )
    runbook = resolve_runbook(settings)
    loaded_prompts = load_prompts(settings, logger)
    log_and_preflight(
        logger, settings, globals_,
        publish_enabled=False, prompts=loaded_prompts,
        review_check=False, publish_check=False,
        runbook=runbook,
    )

    context_data = load_or_collect_context(runbook, settings, None, logger)
    if output_file:
        save_context(context_data, settings, logger)
    preview_run(runbook, settings, context_data, publish_enabled=settings.output.publish)


_RUNBOOK_WORDS = {"runbook", "runbooks"}
_HARNESS_WORDS = {"harness", "harnesses"}
_ALL_WORDS = {"all"}


_LIST_TARGET = Annotated[
    str,
    typer.Argument(
        metavar="[runbooks|harnesses]",
        help="Limit to one section (default: both).",
        show_default=False,
    ),
]


def _run_list(ctx: typer.Context, target: str) -> None:
    from junior.cli.console import error
    from junior.cli.listing import print_listing

    key = target.lower()
    if key not in _RUNBOOK_WORDS | _HARNESS_WORDS | _ALL_WORDS:
        error(f"unknown list target '{target}' (use: runbooks, harnesses, or all)")
        raise typer.Exit(code=2)

    globals_: GlobalOpts = ctx.obj or GlobalOpts()
    settings = build_settings(config=globals_.config)
    if settings.local_runbooks:
        from junior.runbook.registry import load_local_runbooks

        load_local_runbooks(settings.context.project_dir)
    print_listing(
        default_runbook=settings.runbook,
        default_harness=settings.llm.harness_name,
        runbooks=key in _ALL_WORDS | _RUNBOOK_WORDS,
        harnesses=key in _ALL_WORDS | _HARNESS_WORDS,
    )


@app.command("list")
def list_cmd(ctx: typer.Context, target: _LIST_TARGET = "all") -> None:
    """Alias for `junior config list` — list available runbooks and harnesses.

    Shows both sections; `junior list runbooks` / `junior list harnesses` filter
    to one. The `*` marks your configured default; harnesses also show install
    state + readiness.
    """
    _run_list(ctx, target)


_RUNS_TARGET = Annotated[
    str,
    typer.Argument(
        metavar="[list|last]",
        help="`list` (default) shows recent records; `last` prints the newest record's JSON.",
        show_default=False,
    ),
]


@app.command("runs")
def runs_cmd(
    ctx: typer.Context,
    target: _RUNS_TARGET = "list",
    project_dir: ProjectDirArg = None,
) -> None:
    """Browse run records from `<project_dir>/.junior/output/` (the audit trail).

    `junior runs` lists the most recent records (runbook, harness, tokens,
    blocking, summary). `junior runs last` prints the newest record's raw JSON
    to stdout — pipe-safe, e.g. `junior runs last | jq .output`.
    """
    from junior.cli.console import error
    from junior.cli.runs import print_last_run, print_runs_list

    key = target.lower()
    # `junior runs <dir>` (no keyword) — read the target as the project dir.
    if key not in ("list", "last", "latest") and project_dir is None and Path(target).is_dir():
        project_dir, key = Path(target), "list"

    globals_: GlobalOpts = ctx.obj or GlobalOpts()
    settings = build_settings(config=globals_.config, project_dir=project_dir)

    if key == "list":
        ok = print_runs_list(settings)
    elif key in ("last", "latest"):
        ok = print_last_run(settings)
    else:
        error(f"unknown runs target '{target}' (use: list or last)")
        raise typer.Exit(code=2)
    if not ok:
        raise typer.Exit(code=2)


def _run_init() -> None:
    from junior.cli.actions import ensure_interactive_tty
    from junior.init_config import interactive_setup

    ensure_interactive_tty("`junior init`")
    interactive_setup()


@app.command()
def init() -> None:
    """Alias for `junior config init` — interactive setup wizard → YAML."""
    _run_init()


@config_app.command("init")
def config_init() -> None:
    """Interactive setup wizard — pick config location, runbook, harness, publish & output, save as YAML."""
    _run_init()


@config_app.command("list")
def config_list(ctx: typer.Context, target: _LIST_TARGET = "all") -> None:
    """List available runbooks and harnesses (with install state + your defaults).

    Pairs with `config show` (their config fields) and `config env` (their env
    vars). `target` (`runbooks` / `harnesses`) limits to one section. Also
    reachable as the top-level alias `junior list`.
    """
    _run_list(ctx, target)


def _config_source(globals_: GlobalOpts) -> str:
    """Human-readable list of config files that fed the current settings."""
    from junior.cli.settings_builder import used_config_files

    files = used_config_files(globals_)
    return " + ".join(str(p) for p in files) if files else "defaults (no config file)"


@config_app.command("show")
def config_show(
    ctx: typer.Context,
    harness: HarnessOpt = None,
    runbook_name: RunbookOpt = None,
) -> None:
    """Print your current effective config as YAML, scoped to the active setup.

    Resolves the configured harness + runbook (override with --harness /
    --runbook) and prints their context/llm/output fields at your real current
    values, with a header showing where the config loaded from and the harness's
    readiness. Secrets/tokens never appear — see `config env`.
    """
    globals_: GlobalOpts = ctx.obj or GlobalOpts()
    settings = build_settings(config=globals_.config, harness=harness, runbook=runbook_name)
    print_example_config(settings, config_source=_config_source(globals_))


@config_app.command("path")
def config_path() -> None:
    """Print paths of config files (global + local) and whether they exist."""
    from junior.cli.console import console
    from junior.config import (
        GLOBAL_CONFIG_CANDIDATES,
        LOCAL_CONFIG_CANDIDATES,
    )

    console.print("Junior config files (first match in each row wins; later rows override earlier):")

    g = find_global_config()
    if g:
        console.print(f"  [bold]global[/]   {g}")
    else:
        searched = ", ".join(str(p) for p in GLOBAL_CONFIG_CANDIDATES)
        console.print(f"  [bold]global[/]   [dim](none — searched: {searched})[/]")

    local = find_local_config()
    if local:
        console.print(f"  [bold]local[/]    {local.resolve()}")
    else:
        searched = ", ".join(LOCAL_CONFIG_CANDIDATES)
        console.print(f"  [bold]local[/]    [dim](none — searched: {searched})[/]")


@config_app.command("env")
def config_env(
    ctx: typer.Context,
    harness: HarnessOpt = None,
    runbook_name: RunbookOpt = None,
) -> None:
    """Show the env vars a harness + runbook need (API keys, tokens, CI vars).

    Defaults to your configured harness/runbook; override with --harness /
    --runbook. Marks each var required/optional and whether it's set.
    """
    from junior.cli.config_show import print_env_requirements

    globals_: GlobalOpts = ctx.obj or GlobalOpts()
    settings = build_settings(config=globals_.config, harness=harness, runbook=runbook_name)
    print_env_requirements(settings.llm.harness_name, settings.runbook)


def main() -> None:
    """Console-script entry point.

    Exit codes: 0=success, 1=blocking issues, 2=config error, 3=runtime error.
    """
    app()
