"""Run records — a machine-readable trace of every review.

Junior keeps a deterministic, replayable record of what it did: for each run it
writes one JSON file to `.junior/output/{timestamp}.json`. This is the audit
trail that makes "you delegated it, you own it" concrete — you can always see
exactly which runbook + harness ran, on what, and what came back.

Runbook-agnostic: the record is built from the `Runbook` interface
(`name`, `summary`, `is_blocking`) plus the `LLMResult`, so it works for any
runbook, not just code review. Secrets (API keys, tokens) are never included —
only the curated, non-sensitive shape below.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import structlog

from junior.config import Settings
from junior.runbook.base import LLMResult, Runbook

logger = structlog.get_logger()

RECORD_SUBDIR = Path(".junior") / "output"


def record_dir(settings: Settings) -> Path:
    """Where run records live: `<project_dir>/.junior/output/` (next to the repo)."""
    return settings.context.project_dir / RECORD_SUBDIR


def build_record(
    settings: Settings,
    runbook: Runbook,
    result: LLMResult,
    *,
    publish_enabled: bool,
    timestamp: str,
) -> dict:
    """Assemble the (secret-free) run-record dict."""
    return {
        "timestamp": timestamp,
        "runbook": runbook.name,
        "harness": settings.llm.harness_name,
        "model": settings.llm.display_model or None,
        "source": settings.context.source.value,
        "target_branch": settings.context.target_branch,
        "publish": publish_enabled,
        "usage": result.usage.model_dump(),
        "errors": list(result.errors),
        "blocking": runbook.is_blocking(result.output),
        "summary": runbook.summary(result.output),
        "output": result.output.model_dump(mode="json"),
    }


def write_run_record(
    settings: Settings,
    runbook: Runbook,
    result: LLMResult,
    *,
    publish_enabled: bool,
) -> Path | None:
    """Write the run record to `.junior/output/{timestamp}.json`.

    No-op (returns None) when `output.record` is off. Failures to write are
    logged and swallowed — a missing audit file must never fail an otherwise
    successful review.
    """
    if not settings.output.record:
        return None

    now = datetime.now()
    timestamp = now.isoformat(timespec="seconds")
    record = build_record(
        settings, runbook, result,
        publish_enabled=publish_enabled, timestamp=timestamp,
    )
    # `:` is unsafe in filenames on some filesystems; microseconds avoid
    # collisions between two runs in the same second.
    fname = now.strftime("%Y-%m-%dT%H-%M-%S-%f") + ".json"
    try:
        out_dir = record_dir(settings)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / fname
        path.write_text(
            json.dumps(record, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        return path
    except OSError as e:
        logger.warning("could not write run record", error=str(e))
        return None
