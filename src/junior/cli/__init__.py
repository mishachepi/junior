"""CLI package entry point.

The implementation is split across:

- `options`           — reusable Typer option/argument types + panel constants
- `settings_builder`  — Settings construction from JSON config + CLI flags
- `observability`     — structlog setup + startup logging/warnings
- `config_show`       — `junior config show` template renderer
- `actions`           — runbook phase functions (collect/review/publish helpers)
- `app`               — Typer app, callback, subcommand definitions

This file re-exports the public surface (`app`, `main`) plus a few internals
that tests depend on.
"""

from junior.cli.app import app, main
from junior.cli.observability import _startup_warnings


__all__ = ["app", "main", "_startup_warnings"]
