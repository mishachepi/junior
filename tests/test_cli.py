"""Tests for CLI startup warnings and setup guidance."""

from pathlib import Path

from junior.cli import _startup_warnings
from junior.config import HarnessKind, OutputSettings, LLMSettings, Settings


def test_no_setup_warning_for_claudecode_without_config_or_keys():
    settings = Settings(llm=LLMSettings(harness=HarnessKind.CLAUDECODE))

    warnings = list(_startup_warnings(settings, publish_enabled=False, config_files=[]))

    assert warnings == []


def test_setup_warning_for_pydantic_without_config_or_keys():
    settings = Settings(llm=LLMSettings(harness=HarnessKind.PYDANTIC))

    warnings = list(_startup_warnings(settings, publish_enabled=False, config_files=[]))

    assert warnings == [
        "No config file or API keys/tokens detected — run 'junior init' for setup."
    ]


def test_no_setup_warning_when_config_exists(tmp_path):
    settings = Settings(llm=LLMSettings(harness=HarnessKind.PYDANTIC))
    config_file = tmp_path / "config.yaml"
    config_file.write_text("llm:\n  harness: pydantic\n", encoding="utf-8")

    warnings = list(
        _startup_warnings(
            settings, publish_enabled=False, config_files=[Path(config_file)]
        )
    )

    assert warnings == []


def _set_global_config(monkeypatch, tmp_path, text: str) -> Path:
    import junior.config as cfg

    path = tmp_path / "settings.yaml"
    path.write_text(text, encoding="utf-8")
    monkeypatch.setattr(cfg, "GLOBAL_CONFIG_CANDIDATES", (path,))
    return path


def test_warns_when_global_config_switches_runbook(monkeypatch, tmp_path):
    """A `runbook:` in the global config silently changes every repo's default —
    that deserves a startup warning pointing at the project config instead."""
    path = _set_global_config(monkeypatch, tmp_path, "runbook: weather_advice\n")
    settings = Settings(runbook="weather_advice")

    warnings = list(
        _startup_warnings(settings, publish_enabled=False, config_files=[path])
    )

    assert any("global config" in w and "weather_advice" in w for w in warnings)


def test_no_runbook_warning_when_value_comes_from_elsewhere(monkeypatch, tmp_path):
    _set_global_config(monkeypatch, tmp_path, "runbook: weather_advice\n")

    # Effective runbook differs from the global one (e.g. CLI --runbook) — quiet.
    settings = Settings(runbook="github_pr_review")
    assert not any(
        "global config" in w
        for w in _startup_warnings(settings, publish_enabled=False, config_files=[])
    )

    # Default runbook — quiet even if the global file exists.
    assert not any(
        "global config" in w
        for w in _startup_warnings(Settings(), publish_enabled=False, config_files=[])
    )


def test_no_runbook_warning_when_project_config_owns_it(monkeypatch, tmp_path):
    import junior.config as cfg

    _set_global_config(monkeypatch, tmp_path, "runbook: weather_advice\n")
    local = tmp_path / ".junior.yaml"
    local.write_text("runbook: weather_advice\n", encoding="utf-8")
    monkeypatch.setattr(cfg, "LOCAL_CONFIG_CANDIDATES", (str(local),))

    settings = Settings(runbook="weather_advice")
    assert not any(
        "global config" in w
        for w in _startup_warnings(settings, publish_enabled=False, config_files=[])
    )


def test_gitlab_publish_warning_without_inline_sha_context():
    settings = Settings(
        runbook="gitlab_pr_review",
        output=OutputSettings(
            gitlab_token="glpat-xxx", ci_project_id=1, ci_merge_request_iid=2
        ),
    )

    warnings = list(
        _startup_warnings(settings, publish_enabled=True, config_files=[])
    )

    assert warnings == [
        "Inline comments will be skipped — CI_MERGE_REQUEST_DIFF_BASE_SHA / "
        "CI_COMMIT_SHA not set. Only the summary note will be posted."
    ]
