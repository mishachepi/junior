"""`CliHarness.run_cli` — the subprocess plumbing every CLI harness shares."""

import subprocess
from types import SimpleNamespace

import pytest

import junior.harnesses._shared as shared
from junior.config import LLMSettings
from junior.harnesses._shared import CliHarness


class _Fake(CliHarness):
    name = "fake"
    binary = "fakecli"
    install_hint = "install fakecli"

    def complete(self, **kwargs):  # pragma: no cover - not exercised
        raise NotImplementedError


def _capture(monkeypatch, **proc):
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout="", stderr="", **proc)

    monkeypatch.setattr(shared.subprocess, "run", fake_run)
    return captured


def test_run_cli_never_inherits_stdin(monkeypatch):
    """No `input` → the child gets /dev/null, not Junior's stdin (which in a
    pipe chain is the upstream document, and when idle makes codex block on
    «reading additional input from stdin»)."""
    captured = _capture(monkeypatch)
    _Fake().run_cli(["fakecli"], LLMSettings())
    assert captured["kwargs"]["stdin"] is subprocess.DEVNULL
    assert captured["kwargs"]["input"] is None


def test_run_cli_passes_input_on_a_private_pipe(monkeypatch):
    captured = _capture(monkeypatch)
    _Fake().run_cli(["fakecli"], LLMSettings(timeout=42), input="the prompt")
    assert captured["kwargs"]["input"] == "the prompt"
    assert captured["kwargs"]["stdin"] is None  # subprocess makes its own pipe for `input`
    assert captured["kwargs"]["timeout"] == 42


def test_run_cli_translates_missing_binary_and_timeout(monkeypatch):
    def missing(cmd, **kwargs):
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(shared.subprocess, "run", missing)
    with pytest.raises(RuntimeError, match="install fakecli"):
        _Fake().run_cli(["fakecli"], LLMSettings())

    def slow(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(shared.subprocess, "run", slow)
    with pytest.raises(RuntimeError, match="timed out after 7s"):
        _Fake().run_cli(["fakecli"], LLMSettings(timeout=7))
