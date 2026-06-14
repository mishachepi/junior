"""Shared Rich consoles for user-facing output.

Two channels, mirroring the Unix split that structlog already follows
(diagnostics → stderr):

- `console`     → **stdout**. Presentation a human reads: dry-run previews,
  the rendered review, wizard prompts. Rich auto-detects a non-TTY (pipe/file)
  and drops styling, but it still reflows text — so anything that must survive
  a pipe verbatim (review markdown, the env-config template, context JSON) is
  written raw, not through Rich. `print_content()` enforces that boundary.
- `err_console` → **stderr**. Errors, warnings, and status labels, so they
  never pollute piped stdout.

structlog stays the logging channel (stderr); these consoles are strictly for
output the user is meant to read, never for diagnostics.
"""

from __future__ import annotations

import sys

from rich.console import Console

console = Console()
err_console = Console(stderr=True)


def error(message: str) -> None:
    """Print a red error line to stderr."""
    err_console.print(f"[bold red]Error:[/] {message}")


def print_content(text: str) -> None:
    """Write machine-consumable content to stdout verbatim (pipe/redirect safe).

    Use for anything a user may pipe into a file: the review markdown, the
    env-config template, context JSON. No Rich markup, styling, or reflow.
    """
    sys.stdout.write(text)
    if not text.endswith("\n"):
        sys.stdout.write("\n")
