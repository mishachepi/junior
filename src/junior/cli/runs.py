"""`junior runs` — browse the run records under `<project_dir>/.junior/output/`.

The run record is Junior's audit trail ("you delegated it, you own it"); this
is the read side. `junior runs` lists recent records as a table (newest first);
`junior runs last` prints the newest record's JSON raw to stdout, pipe-safe —
e.g. `junior runs last | jq .output`.
"""

from __future__ import annotations

import json
from pathlib import Path

from junior.cli.console import console, error, print_content
from junior.config import Settings

#: how many records `junior runs` lists before cutting off (newest first).
LIST_LIMIT = 20


def _record_files(settings: Settings) -> list[Path]:
    """All record files, newest first (filenames sort chronologically)."""
    from junior.run_record import record_dir

    out_dir = record_dir(settings)
    if not out_dir.is_dir():
        return []
    return sorted(out_dir.glob("*.json"), reverse=True)


def _no_records_msg(settings: Settings) -> str:
    from junior.run_record import record_dir

    return (
        f"no run records in {record_dir(settings)} — "
        "records are written by `junior run` (disable with --no-record)"
    )


def print_runs_list(settings: Settings) -> bool:
    """Render the records table. Returns False when there are none."""
    from rich.table import Table

    files = _record_files(settings)
    if not files:
        error(_no_records_msg(settings))
        return False

    table = Table(show_header=True, header_style="bold")
    # identifying columns must never be truncated; only summary may fold
    for col in ("when", "runbook", "harness"):
        table.add_column(col, no_wrap=True)
    table.add_column("tokens", no_wrap=True, justify="right")
    table.add_column("blocking", no_wrap=True)
    # min_width keeps the header itself from folding ("summ/ary") in narrow terminals
    table.add_column("summary", overflow="fold", min_width=8)

    for path in files[:LIST_LIMIT]:
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            table.add_row(path.stem, "[dim](unreadable)[/]", "", "", "", "")
            continue
        summary = ", ".join(
            f"{k}={v}" for k, v in (rec.get("summary") or {}).items() if v is not None
        )
        tokens = (rec.get("usage") or {}).get("total_tokens") or ""
        blocking = rec.get("blocking")
        ts = str(rec.get("timestamp", path.stem))
        table.add_row(
            # seconds add noise, not identity — the full stamp is in the file name
            ts[:16].replace("T", " "),
            # records from <0.2.0 used "pipeline" for the runbook name
            rec.get("runbook") or rec.get("pipeline", "?"),
            rec.get("harness", "?"),
            str(tokens),
            "[red]yes[/]" if blocking else "no",
            summary[:80],
        )
    console.print(table)
    if len(files) > LIST_LIMIT:
        console.print(f"[dim]… and {len(files) - LIST_LIMIT} older (see .junior/output/)[/]")
    return True


def print_last_run(settings: Settings) -> bool:
    """Print the newest record's JSON raw (stdout, pipe-safe). False if none."""
    files = _record_files(settings)
    if not files:
        error(_no_records_msg(settings))
        return False
    print_content(files[0].read_text(encoding="utf-8").rstrip("\n"))
    return True
