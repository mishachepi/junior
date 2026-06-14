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


def test_local_runbooks_require_opt_in(tmp_path):
    _make_local(tmp_path, "lp_gate")

    # OFF: the local runbook is invisible → unknown runbook → non-zero exit.
    off = tmp_path / "off.yaml"
    off.write_text("runbook: lp_gate\n")
    r_off = runner.invoke(app, ["--config", str(off), "dry-run", "--project-dir", str(tmp_path)])
    assert r_off.exit_code != 0

    # ON: it loads and dry-run works — note no .git in tmp_path (needs_git=False).
    on = tmp_path / "on.yaml"
    on.write_text("local_runbooks: true\nrunbook: lp_gate\n")
    r_on = runner.invoke(app, ["--config", str(on), "dry-run", "--project-dir", str(tmp_path)])
    assert r_on.exit_code == 0, r_on.stdout + r_on.stderr
    assert "lp_gate" in r_on.stdout


def test_needs_git_flag():
    assert registry.get_runbook("local_review").needs_git is True
    assert registry.get_runbook("weather_advice").needs_git is False
