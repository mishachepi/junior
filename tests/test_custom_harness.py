"""A custom harness needs no fork: `--harness pkg.module` imports any module that
exposes a `HARNESS` instance — same escape hatch runbooks have had via
`--runbook pkg.module:Class`. This is also what makes a real echo harness
possible in tests: no LLM, no monkeypatching the registry."""

from __future__ import annotations

import json
import textwrap

import pytest
import yaml
from typer.testing import CliRunner

from junior.cli import app
from junior.config import HarnessKind, LLMSettings, harness_ref

runner = CliRunner()

ECHO_HARNESS = textwrap.dedent('''
    """Test-only harness: fills the requested schema's first field with the user message."""
    from junior.runbook.base import Harness, LLMResult, Usage

    class EchoHarness(Harness):
        name = "echo"

        def is_ready(self):
            return "ready"

        def complete(self, *, system_prompt, user_message, output_schema, llm, project_dir):
            field = next(iter(output_schema.model_fields))
            return LLMResult(output=output_schema(**{field: user_message}), usage=Usage(total_tokens=1))

    HARNESS = EchoHarness()
''')


@pytest.fixture
def echo_module(tmp_path, monkeypatch):
    (tmp_path / "my_echo_harness.py").write_text(ECHO_HARNESS)
    monkeypatch.syspath_prepend(str(tmp_path))
    return "my_echo_harness"


def test_harness_ref_resolves_builtins_paths_and_rejects_typos():
    assert harness_ref("pydantic") is HarnessKind.PYDANTIC
    assert harness_ref("PYDANTIC") is HarnessKind.PYDANTIC
    assert harness_ref("junior.harnesses.codex") is HarnessKind.CODEX
    assert harness_ref("json.decoder") == "json.decoder"    # any importable module: kept for the registry
    with pytest.raises(ValueError, match="unknown harness 'pydantik'"):
        harness_ref("pydantik")                               # not importable → a typo


def test_settings_accept_custom_module_path():
    s = LLMSettings(harness="json.decoder")
    assert s.harness == "json.decoder"
    assert s.harness_name == "json.decoder"
    assert LLMSettings().harness is HarnessKind.PYDANTIC


def test_run_with_custom_harness_module(echo_module, tmp_path):
    """End to end through the CLI: a script runbook + a harness module on sys.path."""
    d = tmp_path / ".junior" / "runbooks" / "shout"
    d.mkdir(parents=True)
    (d / "shout.yaml").write_text(yaml.safe_dump({
        "name": "shout",
        "system_prompt": "Repeat the input.",
        "schema": {"type": "object", "required": ["text"], "properties": {"text": {"type": "string"}}},
    }))
    cfg = tmp_path / "c.yaml"
    cfg.write_text("local_runbooks: true\n")

    result = runner.invoke(
        app,
        [
            "--config", str(cfg), "run", "--runbook", "shout", "--harness", echo_module,
            "--project-dir", str(tmp_path), "--no-record",
        ],
        input="hello from stdin",
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {"text": "hello from stdin"}


def test_custom_harness_shows_in_config_show(echo_module, tmp_path):
    result = runner.invoke(app, ["config", "show", "--harness", echo_module])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert f"harness: {echo_module}" in result.stdout
    assert "ready" in result.stdout
