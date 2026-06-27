"""Tests for repo-local runbooks (.junior/runbooks/) and the needs_git gate."""

import junior.runbook.registry as registry
from junior.cli import app
from typer.testing import CliRunner

runner = CliRunner()


_RUNBOOK_SRC = '''
from pydantic import BaseModel
from junior.config import Settings
from junior.runbook.base import Runbook
from junior.runbook.registry import register_runbook


class Ctx(BaseModel):
    who: str = "world"


class Out(BaseModel):
    text: str


@register_runbook
class P(Runbook[Ctx, Out]):
    name = "{name}"
    description = "local demo {name}"
    context_model = Ctx
    result_model = Out

    def collect(self, settings):
        return Ctx()

    def render(self, c, s, *, file_access):
        return "hi"

    def publish(self, s, r, u, *, errors, publish_enabled):
        from junior.cli.console import console
        console.print(r.text)
'''


def _make_local(base_dir, name, *, folder=True):
    pdir = base_dir / ".junior" / "runbooks"
    pdir.mkdir(parents=True, exist_ok=True)
    src = _RUNBOOK_SRC.format(name=name)
    if folder:
        d = pdir / name
        d.mkdir()
        (d / f"{name}.py").write_text(src)
    else:
        (pdir / f"{name}.py").write_text(src)


def test_load_local_runbook_folder_layout(tmp_path):
    _make_local(tmp_path, "lp_folder")  # .junior/runbooks/lp_folder/lp_folder.py
    loaded = registry.load_local_runbooks(tmp_path)
    assert "lp_folder" in loaded
    assert registry.get_runbook("lp_folder").name == "lp_folder"


def test_load_local_runbook_single_file(tmp_path):
    _make_local(tmp_path, "lp_single", folder=False)  # .junior/runbooks/lp_single.py
    loaded = registry.load_local_runbooks(tmp_path)
    assert "lp_single" in loaded


def test_local_runbooks_loaded_by_default(tmp_path):
    _make_local(tmp_path, "lp_default")

    # Default: local runbooks load with no flag — dry-run works (no .git → needs_git=False).
    cfg = tmp_path / "on.yaml"
    cfg.write_text("runbook: lp_default\n")
    r = runner.invoke(app, ["--config", str(cfg), "dry-run", "--project-dir", str(tmp_path)])
    assert r.exit_code == 0, r.stdout + r.stderr
    assert "lp_default" in r.stdout


def test_local_runbooks_skipped_when_false(tmp_path):
    _make_local(tmp_path, "lp_skip")  # distinct name so the registry isn't pre-populated

    # local_runbooks: false skips discovery → unknown runbook → non-zero exit.
    cfg = tmp_path / "off.yaml"
    cfg.write_text("local_runbooks: false\nrunbook: lp_skip\n")
    r = runner.invoke(app, ["--config", str(cfg), "dry-run", "--project-dir", str(tmp_path)])
    assert r.exit_code != 0


def test_needs_git_flag():
    assert registry.get_runbook("local_review").needs_git is True
    assert registry.get_runbook("weather_advice").needs_git is False
