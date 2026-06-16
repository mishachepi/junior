"""Config views for `junior config show` (your effective config + status) and
`junior config env` (env vars per harness/runbook). Both read declarations off
the Harness/Runbook classes — no central table — so plugins describe themselves."""

from __future__ import annotations

import os

from pydantic_settings import BaseSettings

from junior.cli.console import console, err_console, print_content
from junior.config import (
    ContextSettings,
    HarnessKind,
    LLMSettings,
    OutputSettings,
    Settings,
)

# Group fields that apply to every run (shown in detailed mode regardless of choice).
_UNIVERSAL = {
    "context": ["prompts", "context_files"],
    "llm": [],
    "output": ["record"],
}
_HINTS = {
    "runbook": "which runbook to run — see: junior list",
    "harness": "claudecode | codex | pydantic | deepagents | pi",
    "model": "provider:model (pydantic/deepagents/pi; CLI harnesses use their own)",
    "publish": "run the runbook's publish; else raw output to stdout/-o",
    "output_file": "write the review to a file (empty = stdout)",
    "log_level": "DEBUG | INFO | WARNING | ERROR",
    "local_runbooks": "load .junior/runbooks/ (runs repo code — opt-in)",
    "source": "auto | staged | commit | branch",
    "base_sha": "pin a base commit to diff against",
    "prompts": "task instructions — inline text or file://./path.md",
    "context_files": "extra files for the prompt (key: path)",
    "max_tokens_per_agent": "pydantic: cap response tokens (0 = none)",
    "timeout": "CLI harnesses (claudecode/codex/pi): kill the subprocess after N seconds",
    "permission_mode": "claude CLI: default | acceptEdits | plan | bypassPermissions",
    "max_file_size": "skip files larger than this many bytes",
    "max_diff_chars": "hard cap on inlined diff chars (0 = no limit)",
    "record": "run history / audit trail → .junior/output/{ts}.json (not the result itself)",
    "ci_server_url": "GitLab base URL",
    "bitbucket_url": "Bitbucket DC base URL",
}


def _scalar(value) -> str:
    """Render a Python value as a valid YAML scalar."""
    if isinstance(value, HarnessKind):
        return value.name.lower()  # enum value is a module path, not the short name
    if isinstance(value, bool):
        return "true" if value else "false"
    if hasattr(value, "value"):  # other StrEnum (SourceMode, LogLevel)
        return str(value.value)
    if value is None:
        return "null"
    if value == "":
        return '""'
    if value == []:
        return "[]"
    if value == {}:
        return "{}"
    return str(value)


def _line(field: str, value, indent: int = 0) -> str:
    base = f"{' ' * indent}{field}: {_scalar(value)}"
    hint = _HINTS.get(field)
    return f"{base}{' ' * max(2, 34 - len(base))}# {hint}" if hint else base


def _harness_obj(name: str):
    from junior.runbook.registry import get_harness

    return get_harness(HarnessKind(name))


def _runbook_obj(name: str):
    from junior.runbook.registry import get_runbook

    return get_runbook(name)


def _readiness(kind: HarnessKind) -> str:
    """Short live-status of the resolved harness, for the header comment."""
    from junior.runbook.registry import get_harness, harness_available

    if not harness_available(kind):
        return "✗ not installed"
    try:
        ready = get_harness(kind).is_ready()
    except Exception:
        return "installed"
    return ready or "installed"


def print_example_config(settings: Settings, *, config_source: str) -> None:
    """Print the *current effective* config as YAML, scoped to the active setup.

    The harness + runbook come from `settings` (i.e. your config + any
    `--harness`/`--runbook` override), and only the context/llm/output fields
    *those* actually use are shown — with your real current values. A comment
    header reports where the config was loaded from and the harness's readiness,
    so this doubles as a status view. Secrets and CI vars never appear (see
    `config env`); the body stays valid YAML you can pipe back into a config.
    """
    harness_name = settings.llm.harness_name
    lines = [
        "# Junior — current effective config (YAML; header comments show live status).",
        f"# {'source:':9}{config_source}",
        f"# {'harness:':9}{harness_name} · {_readiness(settings.llm.harness)}",
        f"# {'runbook:':9}{settings.runbook or '(none — set one via junior init or --runbook)'}",
        "",
    ]
    top = [
        ("runbook", settings.runbook),
        ("harness", settings.llm.harness),
        ("model", settings.llm.model),
        ("publish", settings.output.publish),
        ("output_file", settings.output.output_file),
        ("log_level", settings.log_level),
        ("local_runbooks", settings.local_runbooks),
    ]
    lines += [_line(name, value) for name, value in top]

    extra = _resolve_config_fields(settings)
    groups = [
        ("context", ContextSettings, settings.context),
        ("llm", LLMSettings, settings.llm),
        ("output", OutputSettings, settings.output),
    ]
    for group, model, obj in groups:
        wanted = set(_UNIVERSAL[group]) | extra
        fields = [f for f in model.model_fields if f in wanted]
        if not fields:
            continue
        lines.append("")
        lines.append(f"{group}:")
        for field in fields:
            value = getattr(obj, field)
            # A nested settings sub-model (e.g. llm.claudecode) renders as its own
            # indented block, so harness-specific knobs show as `claudecode.<field>`.
            if isinstance(value, BaseSettings):
                lines.append(f"  {field}:")
                lines += [
                    _line(sub, getattr(value, sub), indent=4)
                    for sub in type(value).model_fields
                ]
            else:
                lines.append(_line(field, value, indent=2))
    print_content("\n".join(lines))


def _resolve_config_fields(settings: Settings) -> set[str]:
    """Config field names the *resolved* harness + runbook declare."""
    fields: set[str] = set()
    targets = (
        (settings.llm.harness_name, _harness_obj),
        (settings.runbook, _runbook_obj),
    )
    for name, resolve in targets:
        if not name:  # no runbook configured — nothing to introspect
            continue
        try:
            fields.update(resolve(name).config_fields)
        except Exception as e:  # unknown name or uninstalled extra — skip its fields
            err_console.print(f"[yellow]note:[/] can't introspect '{name}' ({type(e).__name__})")
    return fields


# --- config env -----------------------------------------------------------


def _env_set(var: str) -> bool:
    """True if the env var is set (handles 'A / B' = either is enough)."""
    return any(os.environ.get(name.strip()) for name in var.split("/"))


def _render_env_section(title: str, rows) -> None:
    from rich.table import Table

    if not rows:
        console.print(f"[bold]{title}[/] — no env vars needed.")
        return
    table = Table(title=f"[bold]{title}[/]", title_justify="left", show_edge=False)
    for col in ("env var", "need", "status", "what for"):
        table.add_column(col)
    for var in rows:
        need = "[red]required[/]" if var.required else "[dim]optional[/]"
        status = "[green]✓ set[/]" if _env_set(var.name) else "[yellow]✗ unset[/]"
        table.add_row(var.name, need, status, var.purpose)
    console.print(table)


def print_env_requirements(harness: str, runbook: str) -> None:
    """List the env vars the harness + runbook declare (with set/unset status)."""
    runbook_label = runbook or "(none configured)"
    console.print(
        f"Env vars for harness [bold]{harness}[/] + runbook [bold]{runbook_label}[/]:\n"
    )

    try:
        h = _harness_obj(harness)
        _render_env_section(f"Harness · {harness}", h.env_vars)
        if h.setup_note:
            console.print(f"[dim]{h.setup_note}[/]")
    except Exception as e:
        console.print(f"[bold]Harness · {harness}[/] — not installed ({type(e).__name__}).")

    console.print("")

    if not runbook:
        console.print(
            "[bold]Runbook[/] — none configured; pass --runbook NAME to include its vars."
        )
    else:
        try:
            p = _runbook_obj(runbook)
            _render_env_section(f"Runbook · {runbook}", p.env_vars)
        except Exception as e:
            console.print(f"[bold]Runbook · {runbook}[/] — unavailable ({type(e).__name__}).")

    console.print(
        "\n[dim]Set these in your shell or CI (never in the YAML config). "
        "Many CI_* / GITHUB_* vars are auto-provided by the runner.[/]"
    )
