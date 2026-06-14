"""Render `junior list` — the available runbooks and harnesses.

Discovery surface, separate from config inspection (`config show`/`env`): it
answers "what can I pick for --runbook / --harness", marks the configured
defaults, and tells you which harnesses are installed vs. which need an extra.
"""

from __future__ import annotations

from rich.table import Table

from junior.cli.console import console
from junior.config import HarnessKind
from junior.runbook.registry import (
    HARNESS_META,
    available_runbooks_meta,
    get_harness,
    harness_available,
)


def _section_table() -> Table:
    t = Table(show_header=False, box=None, pad_edge=False, padding=(0, 3, 0, 2))
    t.add_column(style="cyan", no_wrap=True)        # name — never truncate
    t.add_column(no_wrap=True)                       # default marker
    t.add_column(style="dim", overflow="fold")       # description — wrap if narrow
    t.add_column(overflow="fold")                    # status — wrap if narrow
    return t


def _marker(is_default: bool) -> str:
    return "[yellow]*[/]" if is_default else " "


def print_runbooks(default_runbook: str) -> None:
    """List every registered runbook (built-ins + plugins)."""
    console.print("[bold]Runbooks[/]")
    t = _section_table()
    for name, desc in available_runbooks_meta():
        t.add_row(name, _marker(name == default_runbook), desc or "custom runbook", "")
    console.print(t)


def _harness_status(kind: HarnessKind, extra: str) -> str:
    """Install state (cheap, via find_spec) + optional readiness (via is_ready).

    Readiness is only consulted when the harness is installed, and `is_ready`
    is contractually a cheap env/CLI check — so listing never pays for a heavy
    harness import.
    """
    if not harness_available(kind):
        hint = f" [dim](pip install 'junior[{extra}]')[/]" if extra else ""
        return f"[red]✗ not installed[/]{hint}"

    try:
        ready = get_harness(kind).is_ready()
    except Exception:
        ready = None  # installed but its self-check blew up — show install state only
    if ready is None:
        return "[green]✓ installed[/]"
    color = "green" if ready.lower() == "ready" else "yellow"
    return f"[green]✓ installed[/] · [{color}]{ready}[/]"


def print_harnesses(default_harness: str) -> None:
    """List every harness with install state + runtime readiness."""
    console.print("[bold]Harnesses[/]")
    t = _section_table()
    for kind, (desc, extra, _probe) in HARNESS_META.items():
        name = kind.name.lower()
        t.add_row(name, _marker(name == default_harness), desc, _harness_status(kind, extra))
    console.print(t)


def print_listing(
    *,
    default_runbook: str,
    default_harness: str,
    runbooks: bool = True,
    harnesses: bool = True,
) -> None:
    """Print the requested sections, then a footer explaining the `*` marker."""
    if runbooks:
        print_runbooks(default_runbook)
    if runbooks and harnesses:
        console.print()
    if harnesses:
        print_harnesses(default_harness)
    console.print(
        f"\n[dim]* = your configured default "
        f"(runbook={default_runbook}, harness={default_harness}). "
        f"Override per run with --runbook / --harness.[/]"
    )
