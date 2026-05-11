"""Tests for the --interactive run wizard."""

import argparse

from junior import interactive
from junior.config import AgentBackend, Settings


def _args(**kw) -> argparse.Namespace:
    defaults = dict(publish=None, output_file=None, prompts=None)
    defaults.update(kw)
    return argparse.Namespace(**defaults)


def _patch_questions(monkeypatch, answers: dict) -> None:
    """Stub each ask_* function to return a fixed answer from the dict."""
    for name, value in answers.items():
        monkeypatch.setattr(interactive, name, lambda *a, _v=value, **kw: _v)


def test_interactive_run_applies_overrides_to_settings(monkeypatch):
    settings = Settings(agent_backend=AgentBackend.CLAUDECODE)
    args = _args()

    _patch_questions(monkeypatch, {
        "ask_backend": "pydantic",
        "ask_provider": "openai",
        "ask_model": "gpt-5.4-mini",
        "ask_source": "branch",
        "ask_target_branch": "develop",
        "ask_prompts_select": ["security", "logic"],
        "ask_output_mode": "stdout",
        "confirm_run": True,
    })

    new_settings, new_args = interactive.interactive_run(settings, args, ["security", "logic", "design"])

    assert new_settings.agent_backend == AgentBackend.PYDANTIC
    assert new_settings.model_provider == "openai"
    assert new_settings.model_name == "gpt-5.4-mini"
    assert new_settings.source == "branch"
    assert new_settings.ci_merge_request_target_branch_name == "develop"
    assert new_settings.prompts == "security,logic"
    assert new_args.prompts == "security,logic"
    assert new_args.publish is None
    assert new_args.output_file is None


def test_interactive_run_sets_file_output(monkeypatch):
    settings = Settings(agent_backend=AgentBackend.CLAUDECODE)
    args = _args()

    _patch_questions(monkeypatch, {
        "ask_backend": "claudecode",
        "ask_model": "",
        "ask_source": "auto",
        "ask_target_branch": "main",
        "ask_prompts_select": ["security"],
        "ask_output_mode": "file",
        "ask_output_file": "out.md",
        "confirm_run": True,
    })

    new_settings, new_args = interactive.interactive_run(settings, args, ["security"])

    assert new_args.output_file == "out.md"
    assert new_args.publish is None
    assert new_settings.publish_output == "out.md"


def test_interactive_run_sets_publish_mode(monkeypatch):
    settings = Settings(agent_backend=AgentBackend.CLAUDECODE, github_token="ghp_x", github_repository="o/r")
    args = _args()

    _patch_questions(monkeypatch, {
        "ask_backend": "claudecode",
        "ask_model": "",
        "ask_source": "auto",
        "ask_target_branch": "main",
        "ask_prompts_select": ["security"],
        "ask_output_mode": "publish",
        "confirm_run": True,
    })

    new_settings, new_args = interactive.interactive_run(settings, args, ["security"])

    assert new_args.publish == "__auto__"
    assert new_args.output_file is None


def test_interactive_run_cancel_returns_none(monkeypatch):
    settings = Settings(agent_backend=AgentBackend.CLAUDECODE)
    args = _args()

    _patch_questions(monkeypatch, {
        "ask_backend": "pydantic",
        "ask_provider": None,  # user hits Ctrl+C on provider step
    })

    assert interactive.interactive_run(settings, args, ["security"]) is None


def test_interactive_run_confirm_no_returns_none(monkeypatch):
    settings = Settings(agent_backend=AgentBackend.CLAUDECODE)
    args = _args()

    _patch_questions(monkeypatch, {
        "ask_backend": "claudecode",
        "ask_model": "",
        "ask_source": "auto",
        "ask_target_branch": "main",
        "ask_prompts_select": ["security"],
        "ask_output_mode": "stdout",
        "confirm_run": False,
    })

    assert interactive.interactive_run(settings, args, ["security"]) is None


def test_prompts_select_falls_back_when_user_picks_nothing(monkeypatch):
    """Empty selection should keep the previous list, not return an empty one."""
    monkeypatch.setattr(
        interactive.questionary,
        "checkbox",
        lambda *a, **kw: _Asker(answer=[]),
    )

    result = interactive.ask_prompts_select(default=["logic"], available=["logic", "security"])

    assert result == ["logic"]


class _Asker:
    def __init__(self, answer):
        self._answer = answer

    def ask(self):
        return self._answer
