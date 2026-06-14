"""Tests for the manifest-driven ScriptRunbook (B)."""

import pytest
import yaml
from typer.testing import CliRunner

from junior.cli import app
from junior.config import Settings
from junior.runbook.base import Usage
from junior.runbooks.script.runbook import json_schema_to_model, runbook_from_manifest

runner = CliRunner()


def test_json_schema_to_model_builds_fields():
    schema = {
        "type": "object",
        "required": ["a"],
        "properties": {
            "a": {"type": "string"},
            "n": {"type": "integer"},
            "items": {"type": "array", "items": {"type": "string"}},
        },
    }
    model = json_schema_to_model("T", schema)
    inst = model(a="x", items=["y"])
    assert inst.a == "x"
    assert inst.n is None          # optional → default None
    assert inst.items == ["y"]
    with pytest.raises(Exception):  # required field enforced
        model()


def _write_manifest(tmp_path, *, collect="printf 'hi'", publish=None, name="sdemo"):
    d = tmp_path / ".junior" / "runbooks" / "demo"
    d.mkdir(parents=True)
    (d / "schema.json").write_text(
        '{"type":"object","required":["msg"],"properties":{"msg":{"type":"string"}}}'
    )
    manifest = {"name": name, "schema": "schema.json", "collect": collect,
                "system_prompt": "Be terse."}
    if publish:
        manifest["publish"] = publish
    (d / "demo.yaml").write_text(yaml.safe_dump(manifest))
    return d


def test_runbook_from_manifest_collect_render_publish(tmp_path):
    d = _write_manifest(tmp_path, collect="printf 'PAYLOAD'", publish="cat > out.json")
    cls = runbook_from_manifest(d / "demo.yaml")
    pipe = cls()
    settings = Settings(context={"project_dir": str(tmp_path)})

    ctx = pipe.collect(settings)
    assert ctx.payload == "PAYLOAD"
    assert pipe.render(ctx, settings, file_access=False) == "PAYLOAD"
    assert "Be terse." in pipe.system_prompt(settings)
    assert set(cls.result_model.model_fields) == {"msg"}

    # publish (--publish path) pipes the validated result JSON into the command
    pipe.publish(settings, cls.result_model(msg="done"), Usage(), errors=[])
    assert (d / "out.json").read_text().strip() == '{"msg":"done"}'


def test_collect_receives_context_env(tmp_path):
    d = _write_manifest(tmp_path, collect='printf "%s" "$JUNIOR_CONTEXT_WHO"')
    cls = runbook_from_manifest(d / "demo.yaml")
    settings = Settings(context={"project_dir": str(tmp_path), "context": {"who": "Neo"}})
    assert cls().collect(settings).payload == "Neo"


def test_manifest_missing_required_keys_raises(tmp_path):
    d = tmp_path / ".junior" / "runbooks" / "bad"
    d.mkdir(parents=True)
    # neither system_prompt nor collect — nothing left for the AI to do
    (d / "bad.yaml").write_text(yaml.safe_dump({"name": "bad"}))
    with pytest.raises(ValueError):
        runbook_from_manifest(d / "bad.yaml")


def test_manifest_without_schema_gets_default_result_model(tmp_path):
    d = tmp_path / ".junior" / "runbooks" / "minimal"
    d.mkdir(parents=True)
    (d / "minimal.yaml").write_text(yaml.safe_dump(
        {"name": "minimal", "system_prompt": "Answer briefly."}
    ))
    cls = runbook_from_manifest(d / "minimal.yaml")
    assert set(cls.result_model.model_fields) == {"result"}
    inst = cls.result_model(result="ok")
    assert inst.result == "ok"
    with pytest.raises(Exception):  # `result` is required
        cls.result_model()


def test_collect_omitted_reads_stdin(tmp_path, monkeypatch):
    import io

    d = tmp_path / ".junior" / "runbooks" / "chain"
    d.mkdir(parents=True)
    (d / "chain.yaml").write_text(yaml.safe_dump(
        {"name": "chain", "system_prompt": "Review the input."}
    ))
    cls = runbook_from_manifest(d / "chain.yaml")
    settings = Settings(context={"project_dir": str(tmp_path)})

    monkeypatch.setattr("sys.stdin", io.StringIO('{"result": "from previous junior"}'))
    ctx = cls().collect(settings)
    assert ctx.payload == '{"result": "from previous junior"}'


def test_collect_omitted_prefers_positional_input_over_stdin(tmp_path, monkeypatch):
    import io

    d = tmp_path / ".junior" / "runbooks" / "chain"
    d.mkdir(parents=True)
    (d / "chain.yaml").write_text(yaml.safe_dump(
        {"name": "chain", "system_prompt": "Review the input."}
    ))
    cls = runbook_from_manifest(d / "chain.yaml")
    settings = Settings(
        context={"project_dir": str(tmp_path), "input_text": "explicit task text"}
    )

    monkeypatch.setattr("sys.stdin", io.StringIO("piped text — must lose"))
    assert cls().collect(settings).payload == "explicit task text"


def test_collect_omitted_on_tty_is_empty(tmp_path, monkeypatch):
    class _Tty:
        def isatty(self):
            return True

    d = tmp_path / ".junior" / "runbooks" / "chain2"
    d.mkdir(parents=True)
    (d / "chain2.yaml").write_text(yaml.safe_dump(
        {"name": "chain2", "system_prompt": "Review the input."}
    ))
    cls = runbook_from_manifest(d / "chain2.yaml")
    settings = Settings(context={"project_dir": str(tmp_path)})

    monkeypatch.setattr("sys.stdin", _Tty())
    assert cls().collect(settings).payload == ""


def test_dry_run_stdin_collect_via_cli(tmp_path):
    """End-to-end chaining shape: piped stdin becomes the user message."""
    d = tmp_path / ".junior" / "runbooks" / "chained"
    d.mkdir(parents=True)
    (d / "chained.yaml").write_text(yaml.safe_dump(
        {"name": "chained", "system_prompt": "Check the previous step."}
    ))
    cfg = tmp_path / "c.yaml"
    cfg.write_text("local_runbooks: true\nrunbook: chained\n")
    result = runner.invoke(
        app,
        ["--config", str(cfg), "dry-run", "--project-dir", str(tmp_path)],
        input='{"result": "step one output"}',
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "step one output" in result.stdout      # stdin became the user message
    assert "chained_output" in result.stdout       # default schema model built


def test_dry_run_manifest_runbook_via_loader(tmp_path):
    _write_manifest(tmp_path, collect="printf 'hello from script'", name="sdemo_cli")
    cfg = tmp_path / "c.yaml"
    cfg.write_text("local_runbooks: true\nrunbook: sdemo_cli\n")
    result = runner.invoke(app, ["--config", str(cfg), "dry-run", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "hello from script" in result.stdout       # collect ran
    assert "sdemo_cli_output" in result.stdout         # schema built from JSON Schema
