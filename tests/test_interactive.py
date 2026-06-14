"""Tests for the `junior run -i` wizard."""

from pathlib import Path

from junior import interactive
from junior.config import HarnessKind, OutputSettings, LLMSettings, Settings
from junior.interactive import InteractiveIO


def _io(**kw) -> InteractiveIO:
    defaults = dict(output_file=None, publish_enabled=False)
    defaults.update(kw)
    return InteractiveIO(**defaults)


def _patch_questions(monkeypatch, answers: dict) -> None:
    """Stub each ask_* function to return a fixed answer from the dict."""
    answers = {"ask_runbook": "local_review", **answers}  # wizard asks it first
    for name, value in answers.items():
        monkeypatch.setattr(interactive, name, lambda *a, _v=value, **kw: _v)


def test_interactive_run_applies_overrides_to_settings(monkeypatch):
    settings = Settings(llm=LLMSettings(harness=HarnessKind.CLAUDECODE))

    _patch_questions(monkeypatch, {
        "ask_harness": "pydantic",
        "ask_model": "openai:gpt-5.4-mini",
        "ask_source": "branch",
        "ask_target_branch": "develop",
        "ask_output_mode": "stdout",
        "confirm_run": True,
    })

    result = interactive.interactive_run(settings, _io())
    assert result is not None
    new_settings, new_io = result

    assert new_settings.llm.harness == HarnessKind.PYDANTIC
    assert new_settings.llm.resolved_provider == "openai"
    assert new_settings.llm.resolved_model == "gpt-5.4-mini"
    assert new_settings.context.source.value == "branch"
    assert new_settings.context.target_branch == "develop"
    assert new_io.publish_enabled is False
    assert new_io.output_file is None


def test_interactive_run_sets_file_output(monkeypatch):
    settings = Settings(llm=LLMSettings(harness=HarnessKind.CLAUDECODE))

    _patch_questions(monkeypatch, {
        "ask_harness": "claudecode",
        "ask_model": "",
        "ask_source": "auto",
        "ask_target_branch": "main",
        "ask_output_mode": "file",
        "ask_output_file": "out.md",
        "confirm_run": True,
    })

    result = interactive.interactive_run(settings, _io())
    assert result is not None
    new_settings, new_io = result

    assert new_io.output_file == Path("out.md")
    assert new_io.publish_enabled is False
    assert new_settings.output.output_file == "out.md"


def test_interactive_run_sets_publish_mode(monkeypatch):
    settings = Settings(
        llm=LLMSettings(harness=HarnessKind.CLAUDECODE),
        output=OutputSettings(github_token="ghp_x", github_repository="o/r"),
    )

    _patch_questions(monkeypatch, {
        "ask_harness": "claudecode",
        "ask_model": "",
        "ask_source": "auto",
        "ask_target_branch": "main",
        "ask_output_mode": "publish",
        "confirm_run": True,
    })

    result = interactive.interactive_run(settings, _io())
    assert result is not None
    _new_settings, new_io = result

    assert new_io.publish_enabled is True
    assert new_io.output_file is None


def test_interactive_run_cancel_returns_none(monkeypatch):
    settings = Settings(llm=LLMSettings(harness=HarnessKind.CLAUDECODE))

    _patch_questions(monkeypatch, {
        "ask_harness": "pydantic",
        "ask_model": None,  # user hits Ctrl+C on model step
    })

    assert interactive.interactive_run(settings, _io()) is None


def test_interactive_run_switches_runbook(monkeypatch):
    settings = Settings(llm=LLMSettings(harness=HarnessKind.CLAUDECODE))

    _patch_questions(monkeypatch, {
        "ask_runbook": "weather_advice",
        "ask_harness": "claudecode",
        "ask_model": "",
        "ask_source": "auto",
        "ask_target_branch": "main",
        "ask_output_mode": "stdout",
        "confirm_run": True,
    })

    result = interactive.interactive_run(settings, _io())
    assert result is not None
    new_settings, _ = result
    assert new_settings.runbook == "weather_advice"


def test_interactive_run_confirm_no_returns_none(monkeypatch):
    settings = Settings(llm=LLMSettings(harness=HarnessKind.CLAUDECODE))

    _patch_questions(monkeypatch, {
        "ask_harness": "claudecode",
        "ask_model": "",
        "ask_source": "auto",
        "ask_target_branch": "main",
        "ask_output_mode": "stdout",
        "confirm_run": False,
    })

    assert interactive.interactive_run(settings, _io()) is None


def test_interactive_run_file_mode_defaults_to_existing_output_file(monkeypatch):
    """If `-o release.md` was passed before -i, picking 'file' must offer release.md as default."""
    settings = Settings(llm=LLMSettings(harness=HarnessKind.CLAUDECODE))
    io = _io(output_file=Path("release.md"))

    captured: dict = {}

    def _spy_ask_output_file(default):
        captured["default"] = default
        return default

    monkeypatch.setattr(interactive, "ask_output_file", _spy_ask_output_file)
    _patch_questions(monkeypatch, {
        "ask_harness": "claudecode",
        "ask_model": "",
        "ask_source": "auto",
        "ask_target_branch": "main",
        "ask_output_mode": "file",
        "confirm_run": True,
    })

    result = interactive.interactive_run(settings, io)
    assert result is not None
    new_settings, new_io = result

    assert captured["default"] == "release.md"
    assert new_io.output_file == Path("release.md")
    assert new_settings.output.output_file == "release.md"
