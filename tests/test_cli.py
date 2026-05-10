"""Tests for CLI startup warnings and setup guidance."""

import argparse
from pathlib import Path

from junior.cli import _startup_warnings
from junior.config import AgentBackend, Settings


def _args(*, publish: str | None = None) -> argparse.Namespace:
    return argparse.Namespace(publish=publish)


def test_no_setup_warning_for_claudecode_without_config_or_keys():
    settings = Settings(agent_backend=AgentBackend.CLAUDECODE)

    warnings = list(_startup_warnings(settings, _args(), []))

    assert warnings == []


def test_setup_warning_for_pydantic_without_config_or_keys():
    settings = Settings(agent_backend=AgentBackend.PYDANTIC)

    warnings = list(_startup_warnings(settings, _args(), []))

    assert warnings == ["No config file or API keys/tokens detected — run 'junior --init' for setup."]


def test_no_setup_warning_when_config_exists(tmp_path):
    settings = Settings(agent_backend=AgentBackend.PYDANTIC)
    config_file = tmp_path / "config.json"
    config_file.write_text("{}", encoding="utf-8")

    warnings = list(_startup_warnings(settings, _args(), [Path(config_file)]))

    assert warnings == []


def test_gitlab_publish_warning_without_inline_sha_context():
    settings = Settings(gitlab_token="glpat-xxx", ci_project_id=1, ci_merge_request_iid=2)

    warnings = list(_startup_warnings(settings, _args(publish="review.md"), []))

    assert warnings == [
        "Inline comments will be skipped — CI_MERGE_REQUEST_DIFF_BASE_SHA / "
        "CI_COMMIT_SHA not set. Only the summary note will be posted."
    ]
