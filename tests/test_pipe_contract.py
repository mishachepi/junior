"""Pipe contract — `junior run … | junior run …` must compose in a plain shell.

These tests lock the rules every pipeline link relies on. A refactor that
breaks any of them breaks user workflows, however green the unit tests are.

1. Without `--publish`, stdout is **exactly one JSON document** matching the
   runbook's schema — no banners, hints, or logs mixed in.
2. Diagnostics (logs, errors) go to **stderr**.
3. A runbook without a `collect` command reads its user message from **stdin**.
4. Link N's stdout is, byte-for-byte, a valid user message for link N+1.
5. A failed link exits **non-zero with nothing on stdout**, so `set -o pipefail`
   stops the chain instead of feeding garbage downstream.
"""

from __future__ import annotations

import json

import pytest
import yaml
from typer.testing import CliRunner

from junior.cli import app
from junior.runbook.base import LLMResult, Usage

runner = CliRunner()


def _write_link(tmp_path, name: str, field: str) -> None:
    """A minimal script runbook: no `collect` (→ stdin), one string output field."""
    d = tmp_path / ".junior" / "runbooks" / name
    d.mkdir(parents=True)
    (d / f"{name}.yaml").write_text(yaml.safe_dump({
        "name": name,
        "system_prompt": f"You are link '{name}'.",
        "schema": {
            "type": "object",
            "required": [field],
            "properties": {field: {"type": "string"}},
        },
    }))


def _patch_engine(monkeypatch, complete_fn) -> None:
    from junior.runbook import registry

    class _FakeEngine:
        file_access = False

        def complete(self, **kwargs):
            return complete_fn(**kwargs)

    monkeypatch.setattr(registry, "get_harness", lambda kind: _FakeEngine())


@pytest.fixture
def pipeline(tmp_path):
    _write_link(tmp_path, "link1", "draft")
    _write_link(tmp_path, "link2", "final")
    cfg = tmp_path / "c.yaml"
    cfg.write_text("local_runbooks: true\n")
    return tmp_path, cfg


def _invoke(cfg, tmp_path, runbook: str, stdin: str):
    return runner.invoke(
        app,
        [
            "--config", str(cfg), "run",
            "--runbook", runbook, "--harness", "claudecode",
            "--project-dir", str(tmp_path), "--no-record",
        ],
        input=stdin,
    )


def test_two_links_compose_through_stdin(monkeypatch, pipeline):
    tmp_path, cfg = pipeline
    seen: dict[str, str] = {}

    def fake_complete(*, system_prompt, user_message, output_schema, settings):
        field = next(iter(output_schema.model_fields))
        seen[field] = user_message
        return LLMResult(
            output=output_schema(**{field: f"{field} produced by fake"}),
            usage=Usage(total_tokens=1),
        )

    _patch_engine(monkeypatch, fake_complete)

    # link 1: seed text on stdin → one JSON document on stdout
    first = _invoke(cfg, tmp_path, "link1", stdin="seed from the shell")
    assert first.exit_code == 0, first.stdout + first.stderr
    assert seen["draft"] == "seed from the shell"            # rule 3
    out1 = json.loads(first.stdout)                          # rule 1: whole stdout parses
    assert out1 == {"draft": "draft produced by fake"}

    # link 2: link 1's stdout, unchanged, is link 2's stdin
    second = _invoke(cfg, tmp_path, "link2", stdin=first.stdout)
    assert second.exit_code == 0, second.stdout + second.stderr
    assert json.loads(seen["final"]) == out1                 # rule 4: verbatim hand-off
    assert json.loads(second.stdout) == {"final": "final produced by fake"}


def test_stdout_carries_nothing_but_the_document(monkeypatch, pipeline):
    tmp_path, cfg = pipeline

    def fake_complete(*, output_schema, **_):
        return LLMResult(output=output_schema(draft="x"), usage=Usage(total_tokens=1))

    _patch_engine(monkeypatch, fake_complete)
    result = runner.invoke(
        app,
        [
            "--config", str(cfg), "run",
            "--runbook", "link1", "--harness", "claudecode",
            "--project-dir", str(tmp_path), "--no-record", "--verbose",
        ],
        input="seed",
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {"draft": "x"}       # rule 1, even with --verbose
    assert result.stderr, "verbose diagnostics must exist — and live on stderr"  # rule 2
    assert "review complete" not in result.stdout


def test_failed_link_exits_nonzero_with_empty_stdout(monkeypatch, pipeline):
    tmp_path, cfg = pipeline

    def fake_complete(**_):
        raise RuntimeError("model unavailable")

    _patch_engine(monkeypatch, fake_complete)
    result = _invoke(cfg, tmp_path, "link1", stdin="seed")
    assert result.exit_code != 0                             # rule 5
    assert result.stdout == ""                               # nothing half-written
    assert "model unavailable" in result.stderr


def test_config_from_stdin_cannot_also_feed_the_runbook(monkeypatch, pipeline):
    """`--config -` swallows stdin; a collect-less runbook then silently sees an
    empty user message. That must be a loud error, not an empty LLM call."""
    tmp_path, cfg = pipeline
    called = []

    def fake_complete(**_):
        called.append(True)
        raise AssertionError("harness must not run")

    _patch_engine(monkeypatch, fake_complete)
    result = runner.invoke(
        app,
        [
            "--config", "-", "run",
            "--runbook", "link1", "--harness", "claudecode",
            "--project-dir", str(tmp_path), "--no-record",
        ],
        input=cfg.read_text(),
    )
    assert result.exit_code != 0
    assert result.stdout == ""
    assert called == []
    assert "--config -" in result.stderr and "stdin" in result.stderr
