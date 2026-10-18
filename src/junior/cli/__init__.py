"""CLI package entry point.

The implementation is split across:

- `options`           — reusable Typer option/argument types + panel constants
- `settings_builder`  — Settings construction from YAML config + CLI flags
- `observability`     — structlog setup + startup logging/warnings
- `config_show`       — `junior config show` / `config env` renderers
- `listing`           — `junior list` tables
- `runs`              — `junior runs` (run records)
- `console`           — stdout/stderr consoles + `error()`
- `actions`           — runbook phase functions (collect/review/publish helpers)
- `app`               — Typer app, callback, subcommand definitions

This file re-exports the public surface (`app`, `main`) plus a few internals
that tests depend on.
"""

from junior.cli.app import app, main
from junior.cli.observability import _startup_warnings

__all__ = ["_startup_warnings", "app", "main"]
