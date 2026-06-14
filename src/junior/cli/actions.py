"""Subcommand actions — what the Typer commands actually do once flags are parsed.

These functions form the runbook (collect → review → publish) plus the
ancillary actions for `dry-run` and the interactive wizard. The Typer
command bodies in `cli.app` are thin wrappers around these.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from junior.cli.console import console, error
from junior.config import Settings
from junior.interactive import InteractiveIO


def resolve_runbook(settings: Settings):
    """Look up the selected runbook. Exits on a bad name.

    When `settings.local_runbooks` is on, repo-local runbooks from
    `<project>/.junior/runbooks/` are loaded first (opt-in; executes repo code).
    """
    from junior.runbook.registry import get_runbook

    if not settings.runbook:
        # Deliberately no implicit default — the runbook is always an explicit
        # choice, so a run never silently does something the user didn't pick.
        error(
            "no runbook configured — pass --runbook NAME, set RUNBOOK, or set "
            "`runbook:` in your config (`junior init` sets one up; "
            "`junior config list` shows what's available)"
        )
        raise typer.Exit(code=2)

    if settings.local_runbooks:
        from junior.runbook.registry import load_local_runbooks

        load_local_runbooks(settings.context.project_dir)

    try:
        return get_runbook(settings.runbook)
    except ValueError as e:
        error(str(e))
        raise typer.Exit(code=2)


def resolve_harness(settings: Settings):
    """Look up the LLM harness for the configured `llm.harness`.

    Exits cleanly (code 3) when the harness's optional dependency isn't
    installed — e.g. `--harness pydantic` on a core install — instead of leaking
    an ImportError traceback.
    """
    from junior.runbook.registry import get_harness

    try:
        return get_harness(settings.llm.harness)
    except Exception as e:
        harness = settings.llm.harness_name
        error(
            f"harness '{harness}' is unavailable: {e}\n"
            f"Install its extra, e.g. `uv tool install 'junior[{harness}]'`."
        )
        raise typer.Exit(code=3)


def load_prompts(settings: Settings, logger) -> list:
    """Resolve `settings.context.prompts` into Prompt objects (for preflight/log).

    Each entry is either inline text or a `file://...` URI (absolute by the
    time it reaches Settings). Empty result is fine.
    """
    from junior.prompt_loader import load_prompts as resolve

    try:
        return resolve(list(settings.context.prompts))
    except ValueError as e:
        error(str(e))
        raise typer.Exit(code=2)


def load_or_collect_context(
    runbook,
    settings: Settings,
    from_file: Optional[Path],
    logger,
):
    """Phase 1: load the runbook's context from --from-file JSON, or collect it."""
    if from_file:
        try:
            ctx = runbook.context_model.model_validate_json(
                from_file.read_text(encoding="utf-8")
            )
        except FileNotFoundError:
            logger.error("context file not found", path=str(from_file))
            raise typer.Exit(code=2)
        except Exception as e:
            logger.error("failed to load context file", path=str(from_file), error=str(e))
            raise typer.Exit(code=3)
        logger.debug("context loaded from file", path=str(from_file))
        return ctx

    logger.debug("phase 1: collecting context", runbook=runbook.name)
    try:
        ctx = runbook.collect(settings)
    except Exception as e:
        logger.error("collection failed", error=str(e))
        raise typer.Exit(code=3)

    logger.debug("collection complete")
    return ctx


def preview_run(runbook, settings: Settings, context, *, publish_enabled: bool) -> None:
    """Print a full no-AI preview: the plan (runbook/harness/schema/publish),
    the collected context, and the exact system prompt + user message the harness
    would receive. Everything goes to stdout (logs stay on stderr)."""
    from rich.rule import Rule
    from rich.table import Table

    from junior.runbook.runner import merge_system_prompt

    # Resolve the harness for file_access; tolerate it not being installed so a
    # preview still works (file_access only changes whether the diff is inlined).
    harness_name = settings.llm.harness_name
    file_access = False
    harness_note = ""
    try:
        from junior.runbook.registry import get_harness

        file_access = get_harness(settings.llm.harness).file_access
    except Exception as e:  # missing optional dep — preview anyway
        harness_note = f" — not installed ({type(e).__name__}); assuming file_access=False"

    # --- Context summary ---
    console.print(Rule("Context"))
    _print_context_summary(context)
    if runbook.is_empty(context):
        console.print(
            "[yellow]Context is empty — `junior run` would stop here without calling the LLM.[/]"
        )

    # --- Exactly what the harness receives ---
    system_prompt = merge_system_prompt(
        runbook.system_prompt(settings), list(settings.llm.system_prompt)
    )
    user_message = runbook.render(context, settings, file_access=file_access)
    console.print(Rule(f"System prompt — {len(system_prompt)} chars"))
    if system_prompt:
        console.print(system_prompt, markup=False, highlight=False)
    else:
        console.print("[dim](empty)[/]")
    console.print(Rule(f"User message — {len(user_message)} chars (file_access={file_access})"))
    console.print(user_message, markup=False, highlight=False)

    # --- Output schema (what the harness must return) ---
    result_model = runbook.result_model
    from rich.markup import escape

    console.print(Rule("Output schema"))
    console.print(f"[bold]{result_model.__name__}[/]")
    for fname, field in result_model.model_fields.items():
        optional = "" if field.is_required() else "  [dim](optional)[/]"
        # escape the type — e.g. `list[str]` must not be read as Rich markup.
        console.print(f"  [cyan]{escape(fname)}[/]: {escape(_type_name(field.annotation))}{optional}")

    # --- Plan (summary, last — after everything that feeds the harness) ---
    plan = Table(show_header=False, box=None, pad_edge=False)
    plan.add_column(style="bold cyan")
    plan.add_column()
    plan.add_row("runbook", runbook.name)
    plan.add_row("harness", f"{harness_name}  (file_access={file_access}){harness_note}")
    plan.add_row("model", settings.llm.display_model or "(harness default)")
    plan.add_row("publish", str(publish_enabled))
    plan.add_row("record", str(settings.output.record))
    plan.add_row("output schema", result_model.__name__)
    console.print(Rule("Plan"))
    console.print(plan)


def _print_context_summary(context) -> None:
    """Dry-run context view. Shows the code-review changed-files table when the
    context has that shape; otherwise a generic dump of the context model's
    fields, so any runbook's context previews without special-casing."""
    from rich.table import Table

    changed = getattr(context, "changed_files", None)
    if changed is not None and hasattr(context, "full_diff"):
        branches = (
            f"   {context.source_branch} → {context.target_branch}"
            if getattr(context, "source_branch", "") else ""
        )
        console.print(f"{len(changed)} files, {len(context.full_diff)} chars diff{branches}")
        if getattr(context, "mr_title", ""):
            console.print(f"MR/PR: {context.mr_title}")
        table = Table(show_header=True, header_style="bold")
        for col, kw in (("status", {}), ("file", {}),
                        ("+", {"justify": "right", "style": "green"}),
                        ("-", {"justify": "right", "style": "red"})):
            table.add_column(col, **kw)
        for f in changed:
            added = sum(
                1 for line in f.diff.splitlines()
                if line.startswith("+") and not line.startswith("+++")
            ) if f.diff else 0
            removed = sum(
                1 for line in f.diff.splitlines()
                if line.startswith("-") and not line.startswith("---")
            ) if f.diff else 0
            table.add_row(f.status.value, f.path, f"+{added}", f"-{removed}")
        console.print(table)
        return

    # Generic context (e.g. a non-code-review runbook): list its fields.
    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_column(style="bold cyan")
    table.add_column(overflow="fold")
    for name, value in context.model_dump().items():
        table.add_row(name, _short_value(value))
    console.print(table)


def _type_name(annotation) -> str:
    """Readable name for a pydantic field annotation (e.g. `list[OutfitItem]`)."""
    import typing

    origin = typing.get_origin(annotation)
    if origin is None:
        name = getattr(annotation, "__name__", str(annotation).replace("typing.", ""))
        return "None" if name == "NoneType" else name
    args = ", ".join(_type_name(a) for a in typing.get_args(annotation))
    oname = getattr(origin, "__name__", str(origin).replace("typing.", ""))
    return f"{oname}[{args}]" if args else oname


def _short_value(value) -> str:
    """Compact one-line rendering of a context field value for the preview."""
    if isinstance(value, list):
        return f"[{len(value)} item{'s' if len(value) != 1 else ''}]"
    if isinstance(value, dict):
        return f"{{{len(value)} key{'s' if len(value) != 1 else ''}}}"
    text = str(value)
    return text if len(text) <= 200 else text[:197] + "…"


def save_context(context, settings: Settings, logger) -> None:
    """Save any runbook's context model as JSON (for `run --from-file`)."""
    output = settings.output.output_file or "context.json"
    Path(output).write_text(context.model_dump_json(indent=2), encoding="utf-8")
    changed = getattr(context, "changed_files", None)
    logger.info(
        "context saved",
        path=output,
        context=type(context).__name__,
        changed_files=len(changed) if changed is not None else None,
    )


def run_review(
    runbook,
    harness,
    context,
    settings: Settings,
    *,
    publish_enabled: bool,
    logger,
):
    """Phase 2+3: harness produces the result schema; runbook publishes it.

    Thin CLI wrapper around `runner.run_runbook` — adds logging and turns
    failures into a clean `typer.Exit`. Returns the LLMResult.
    """
    from junior.runbook.runner import run_runbook

    logger.debug(
        "phase 2: AI review starting",
        harness=settings.llm.harness_name,
        runbook=runbook.name,
    )
    try:
        result = run_runbook(
            runbook, harness, context, settings, publish_enabled=publish_enabled
        )
    except typer.Exit:
        raise
    except Exception as e:
        logger.error("review failed", error=str(e))
        raise typer.Exit(code=3)

    logger.debug(
        "review complete",
        tokens_used=result.usage.total_tokens,
        **runbook.summary(result.output),
    )

    from junior.run_record import write_run_record

    record_path = write_run_record(
        settings, runbook, result, publish_enabled=publish_enabled
    )
    if record_path is not None:
        logger.info("run recorded", path=str(record_path))

    return result


def _stdout_is_tty() -> bool:
    """Whether stdout is an interactive terminal (False in pipes/CI/tests)."""
    import sys

    try:
        return sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def ensure_interactive_tty(what: str) -> None:
    """Exit 2 with a clean message when a wizard would run without a terminal.

    questionary needs a real TTY on stdin; without this guard it dies with a
    raw asyncio traceback (observed with `junior init </dev/null` and in CI)."""
    import sys

    try:
        if sys.stdin is not None and sys.stdin.isatty():
            return
    except (AttributeError, ValueError):
        pass
    error(
        f"{what} is interactive and needs a terminal (stdin is not a TTY). "
        "Use flags or a config file instead — see `junior config show` / docs."
    )
    raise typer.Exit(code=2)


def emit_output(runbook, settings: Settings, result_output, logger) -> None:
    """Default (no `--publish`) sink: write the runbook's raw `render_output()`
    to `-o FILE`, or stdout. Pipe-/redirect-safe — never Rich-formatted.

    The output itself is deterministic (same bytes in a terminal and a pipe);
    only a discoverability hint is added on stderr when a human is watching."""
    text = runbook.render_output(result_output)
    out_file = settings.output.output_file
    if out_file:
        ending = "" if text.endswith("\n") else "\n"
        Path(out_file).write_text(text + ending, encoding="utf-8")
        logger.info("output written", path=out_file)
    else:
        from junior.cli.console import err_console, print_content

        print_content(text)
        if _stdout_is_tty():
            err_console.print(
                f"\n[dim]Hint: this is the raw result (pipe-safe). "
                f"--publish runs '{runbook.name}'s formatted publish step instead.[/]"
            )


def publish_pre_generated(settings: Settings, review_file: Path, runbook, logger) -> None:
    """Skip collect+review; publish a pre-generated review .md via the runbook."""
    try:
        markdown = review_file.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.error("review file not found", path=str(review_file))
        raise typer.Exit(code=2)

    logger.info("publishing pre-generated review", path=str(review_file), runbook=runbook.name)
    try:
        runbook.publish_prepared(settings, markdown)
    except Exception as e:
        logger.error("publish failed", runbook=runbook.name, error=str(e))
        raise typer.Exit(code=3)
    logger.info("published successfully", runbook=runbook.name)


def run_interactive(
    settings: Settings,
    io_in: InteractiveIO,
) -> tuple[Settings, InteractiveIO]:
    """Walk the interactive wizard. Returns (new_settings, new_io). Exits on cancel."""
    from junior.interactive import interactive_run

    ensure_interactive_tty("`junior run -i`")
    outcome = interactive_run(settings, io_in)
    if outcome is None:
        raise typer.Exit()
    return outcome
