"""Logging setup and startup diagnostics.

Logs go to stderr (Unix convention — stdout is reserved for the program's
actual output: review markdown, context JSON, dry-run preview). The custom
`_drop_none` processor strips key=None pairs so structured log lines stay
focused on what actually has a value.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import structlog

from junior.config import HarnessKind, Settings


def _drop_empty(_logger, _method, event_dict: dict) -> dict:
    """structlog processor: omit key=value pairs where value is None or empty.

    Empty strings / empty lists / empty dicts add visual noise without
    information (`mr_title=` in a structured line tells you nothing).
    The "event" key itself is preserved unconditionally — it's the
    log line's headline.
    """
    return {
        k: v for k, v in event_dict.items()
        if k == "event" or (v is not None and v != "" and v != [] and v != {})
    }


def setup_logging(log_level: str = "INFO") -> None:
    """Configure structlog: stderr output, None values dropped, level filter."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    structlog.configure(
        processors=[
            _drop_empty,
            structlog.processors.TimeStamper(fmt="%H:%M:%S"),
            structlog.processors.add_log_level,
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.WriteLoggerFactory(file=sys.stderr),
    )


def _global_runbook_override(settings: Settings) -> str | None:
    """Warn when the effective runbook was switched by the *global* config.

    A `runbook:` in `~/.config/junior/` changes what a bare `junior run` does in
    every repository — the most surprising sticky default (e.g. an example
    runbook left over from an experiment). Only fires when that value is what
    actually took effect: an env var, project config, or CLI flag setting the
    runbook suppresses it.
    """
    import os

    from junior.config import find_global_config, find_local_config, load_config_file

    default = Settings.model_fields["runbook"].default
    if settings.runbook == default or "RUNBOOK" in os.environ:
        return None
    global_path = find_global_config()
    if global_path is None:
        return None

    def _safe_load(path: Path) -> dict:
        try:
            return load_config_file(path)
        except (ValueError, OSError):
            return {}

    if _safe_load(global_path).get("runbook") != settings.runbook:
        return None  # the effective value came from elsewhere (CLI/--config/local)
    local_path = find_local_config()
    if local_path is not None and "runbook" in _safe_load(local_path):
        return None  # project config owns the choice — that's the intended place
    return (
        f"runbook '{settings.runbook}' comes from the global config ({global_path}) "
        "and applies to every repository. Prefer the project config (.junior.yaml) "
        "or --runbook; `junior config show` displays the effective setup."
    )


def _startup_warnings(
    settings: Settings,
    *,
    publish_enabled: bool,
    config_files: list[Path],
):
    """Yield soft warnings to surface at startup. Hard errors go through preflight()."""
    runbook_hint = _global_runbook_override(settings)
    if runbook_hint:
        yield runbook_hint

    has_auth = any(
        [
            settings.llm.openai_api_key,
            settings.llm.anthropic_api_key,
            settings.output.gitlab_token,
            settings.output.github_token,
        ]
    )
    needs_setup = settings.llm.harness in (HarnessKind.PYDANTIC, HarnessKind.DEEPAGENTS)
    if not config_files and not has_auth and needs_setup:
        yield "No config file or API keys/tokens detected — run 'junior init' for setup."

    if (
        publish_enabled
        and settings.runbook == "gitlab_pr_review"
        and not (
            settings.output.ci_merge_request_diff_base_sha
            and settings.output.ci_commit_sha
        )
    ):
        yield (
            "Inline comments will be skipped — CI_MERGE_REQUEST_DIFF_BASE_SHA / "
            "CI_COMMIT_SHA not set. Only the summary note will be posted."
        )


def log_startup(
    logger,
    settings: Settings,
    *,
    publish_enabled: bool,
    prompts: list,
    config_files: list[Path],
) -> None:
    """One-line startup banner with the settings that matter.

    Logged at INFO so every run announces *what it's about to do* up front —
    which runbook, harness, source, and whether it will publish. This is the
    main guard against a sticky config default (e.g. a global `runbook:`) running
    something other than the user expected without any visible cue. None/empty
    fields are dropped by the `_drop_empty` processor so the line stays focused;
    it goes to stderr, so stdout stays pipe-safe.
    """
    logger.info(
        "starting",
        harness=settings.llm.harness_name,
        model=settings.llm.display_model or None,
        source=f"{settings.context.source.value} vs {settings.context.target_branch}",
        runbook=settings.runbook,
        publish=publish_enabled or None,
        prompts=[p.name for p in prompts] if prompts else None,
        config_files=[str(p) for p in config_files] or None,
        context_keys=list(settings.context.context.keys()) or None,
        context_file_keys=list(settings.context.context_files.keys()) or None,
    )
    for w in _startup_warnings(
        settings, publish_enabled=publish_enabled, config_files=config_files
    ):
        logger.warning("startup_hint", message=w)
