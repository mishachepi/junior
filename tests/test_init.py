"""Tests for the `junior init` wizard (interactive_setup)."""

import yaml

import junior.init_config as init_mod
from junior import config as config_module


def _patch_answers(monkeypatch, **answers) -> None:
    """Stub the ask_* primitives that interactive_setup looks up."""
    for name, value in answers.items():
        monkeypatch.setattr(init_mod, name, lambda *a, _v=value, **kw: _v)


def test_init_global_full(tmp_path, monkeypatch):
    """Global target with a platform runbook writes runbook/harness/model/publish/output."""
    cfg = tmp_path / "settings.yaml"
    monkeypatch.setattr(config_module, "GLOBAL_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "GLOBAL_CONFIG_PATH", cfg)
    monkeypatch.setattr(init_mod, "GLOBAL_CONFIG_PATH", cfg)  # the name init looks up

    _patch_answers(
        monkeypatch,
        ask_config_target="global",
        ask_runbook="github_pr_review",
        ask_harness="pydantic",
        ask_model="anthropic:claude-opus-4-6",
        ask_publish=True,
        ask_output_file="review.md",
    )

    init_mod.interactive_setup()

    saved = yaml.safe_load(cfg.read_text())
    assert saved == {
        "runbook": "github_pr_review",
        "harness": "pydantic",
        "model": "anthropic:claude-opus-4-6",
        "publish": True,
        "output_file": "review.md",
    }


def test_init_local_minimal(tmp_path, monkeypatch):
    """Local target with local_review skips publish; empty output stays stdout."""
    monkeypatch.chdir(tmp_path)

    _patch_answers(
        monkeypatch,
        ask_config_target="local",
        ask_runbook="local_review",
        ask_harness="claudecode",
        ask_output_file="",  # stdout
    )

    init_mod.interactive_setup()

    cfg = tmp_path / ".junior.yaml"
    assert cfg.is_file()
    saved = yaml.safe_load(cfg.read_text())
    # local_review can't publish and stdout output → just runbook + harness (flat)
    assert saved == {"runbook": "local_review", "harness": "claudecode"}


def test_init_cancel_at_target_writes_nothing(tmp_path, monkeypatch):
    """Ctrl+C (None) on the first prompt must not write any file."""
    cfg = tmp_path / "settings.yaml"
    monkeypatch.setattr(config_module, "GLOBAL_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "GLOBAL_CONFIG_PATH", cfg)
    monkeypatch.setattr(init_mod, "GLOBAL_CONFIG_PATH", cfg)
    monkeypatch.chdir(tmp_path)

    _patch_answers(monkeypatch, ask_config_target=None)

    init_mod.interactive_setup()

    assert not cfg.exists()
    assert not (tmp_path / ".junior.yaml").exists()
