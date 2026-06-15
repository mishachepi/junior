"""Smoke tests for Typer subcommands via CliRunner.

Verifies wiring of the CLI: that each subcommand registers, parses --help
without crashing, and that command-specific behavior reaches its target.

The bottom block (end-to-end runbook) exercises `junior run` from argv
to exit-code with all three phases mocked at the module-attribute level —
this catches CLI/runbook plumbing regressions that unit tests miss.
"""

from typer.testing import CliRunner

from junior.cli import app
from junior import __version__
from junior.models import (
    ChangedFile,
    CollectedContext,
    FileStatus,
    Recommendation,
)


runner = CliRunner()


# --- Top-level ---


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_top_help_lists_all_subcommands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("run", "dry-run", "list", "init", "config"):
        assert cmd in result.stdout


def test_context_command_removed():
    """`context` was folded into `dry-run -o` — it must no longer exist."""
    result = runner.invoke(app, ["context", "--help"])
    assert result.exit_code != 0


def test_no_args_shows_help_and_exits_nonzero():
    """`junior` alone — show help, exit non-zero (Click convention)."""
    result = runner.invoke(app, [])
    assert result.exit_code != 0
    assert "Commands" in result.stdout or "commands" in result.stdout.lower()


def test_unknown_command_errors():
    result = runner.invoke(app, ["frobnicate"])
    assert result.exit_code != 0


# --- Per-subcommand --help (smoke: no crash, panels present) ---


def test_run_help_has_grouped_panels():
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    for panel in (
        "Context — what to review",
        "Review — how to review",
        "Output — where to send",
        "Operational",
    ):
        assert panel in result.stdout


def test_dry_run_help_mirrors_run_flags():
    """`dry-run` previews a real run, so it exposes the same review flags."""
    result = runner.invoke(app, ["dry-run", "--help"])
    assert result.exit_code == 0
    assert "--harness" in result.stdout
    assert "--publish" in result.stdout
    assert "--output-file" in result.stdout  # -o saves context for --from-file
    assert "--verbose" in result.stdout  # -v works after the subcommand too


def test_verbose_after_subcommand(monkeypatch, tmp_path):
    """`junior dry-run -v` (flag after the command) must parse, not error."""
    _make_git_repo(tmp_path)
    import junior.collect.local

    monkeypatch.setattr(junior.collect.local, "collect", lambda s: _fake_context())
    result = runner.invoke(app, ["dry-run", "--runbook", "local_review", "--verbose", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0, result.stdout + result.stderr


def test_env_flag_feeds_settings(monkeypatch, tmp_path):
    """--env KEY=VALUE is applied before Settings are built (env precedence)."""
    import os

    _make_git_repo(tmp_path)
    import junior.collect.local

    monkeypatch.setattr(junior.collect.local, "collect", lambda s: _fake_context())
    monkeypatch.setenv("HARNESS", "claudecode")  # registers teardown restore
    result = runner.invoke(app, ["dry-run", "--runbook", "local_review", "--env", "HARNESS=codex", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert os.environ["HARNESS"] == "codex"
    assert "codex" in result.stdout  # the plan reflects the harness from --env


def test_env_flag_rejects_malformed_pair(tmp_path):
    result = runner.invoke(app, ["run", "--env", "NO_EQUALS_SIGN", "--project-dir", str(tmp_path)])
    assert result.exit_code == 2
    assert "KEY=VALUE" in result.stdout + result.stderr


def test_config_flag_is_env_alias(monkeypatch, tmp_path):
    """A scalar config flag like --model is sugar for --env: it lands in
    os.environ (inherited by subprocesses) and wins over an exported env var."""
    import os

    _make_git_repo(tmp_path)
    import junior.collect.local

    monkeypatch.setattr(junior.collect.local, "collect", lambda s: _fake_context())
    monkeypatch.setenv("MODEL", "env-model")  # exported env loses to the flag
    result = runner.invoke(app, ["dry-run", "--runbook", "local_review", "--model", "flag-model", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert os.environ["MODEL"] == "flag-model"


def test_primary_selector_flags_are_not_exported(monkeypatch, tmp_path):
    """--harness / --runbook select what THIS process runs: they beat env but
    are never exported (a nested `junior run` must not inherit them)."""
    import os

    _make_git_repo(tmp_path)
    import junior.collect.local

    monkeypatch.setattr(junior.collect.local, "collect", lambda s: _fake_context())
    monkeypatch.setenv("HARNESS", "claudecode")
    result = runner.invoke(app, ["dry-run", "--runbook", "local_review", "--harness", "codex", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "codex" in result.stdout  # the flag still wins over env...
    assert os.environ["HARNESS"] == "claudecode"  # ...but env is untouched
    assert "RUNBOOK" not in os.environ


def test_positional_input_text_reviews_text_not_diff(tmp_path):
    """`junior run "some text"` hands the text to collect — code_review then
    reviews it instead of a git diff, and no git repo is required."""
    # tmp_path is NOT a git repo on purpose.
    result = runner.invoke(
        app,
        ["dry-run", "--runbook", "local_review", "--project-dir", str(tmp_path),
         "def f(user_id): return db.execute(f'SELECT * WHERE id={user_id}')"],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "db.execute" in result.stdout  # the text reached the user message


def test_input_text_conflicts_with_from_file(tmp_path):
    """Positional INPUT must not be silently dropped when --from-file/--publish-file
    already supply the run's input."""
    _make_git_repo(tmp_path)
    ctx = tmp_path / "ctx.json"
    ctx.write_text("{}")
    result = runner.invoke(
        app,
        ["run", "--runbook", "local_review", "--from-file", str(ctx),
         "--project-dir", str(tmp_path), "stray text"],
    )
    assert result.exit_code == 2
    assert "INPUT conflicts" in result.stdout + result.stderr


def test_unknown_harness_is_a_human_error(tmp_path):
    """A bad --harness must name the known harnesses, not pydantic's module paths."""
    _make_git_repo(tmp_path)
    result = runner.invoke(
        app, ["run", "--runbook", "local_review", "--harness", "nope", "--project-dir", str(tmp_path)]
    )
    assert result.exit_code == 2
    out = result.stdout + result.stderr
    assert "unknown harness 'nope'" in out
    assert "claudecode" in out and "pi" in out
    assert "junior.harnesses" not in out


def test_run_without_runbook_is_a_clear_config_error(tmp_path):
    """No implicit default runbook: unconfigured `junior run` exits 2 with a hint."""
    _make_git_repo(tmp_path)
    result = runner.invoke(app, ["run", "--project-dir", str(tmp_path)])
    assert result.exit_code == 2
    out = result.stdout + result.stderr
    assert "no runbook configured" in out
    assert "--runbook" in out and "junior init" in out


def test_flag_wins_over_env_flag_pair(monkeypatch, tmp_path):
    """When both are given, the dedicated flag beats its own --env pair."""
    _make_git_repo(tmp_path)
    import junior.collect.local

    monkeypatch.setattr(junior.collect.local, "collect", lambda s: _fake_context())
    result = runner.invoke(
        app,
        ["dry-run", "--runbook", "local_review", "--env", "HARNESS=claudecode", "--harness", "codex", "--project-dir", str(tmp_path)],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "codex" in result.stdout


def test_init_help():
    result = runner.invoke(app, ["init", "--help"])
    assert result.exit_code == 0
    assert "setup" in result.stdout.lower()


def test_config_help_lists_show_and_path():
    result = runner.invoke(app, ["config", "--help"])
    assert result.exit_code == 0
    assert "show" in result.stdout
    assert "path" in result.stdout


# --- Behavior of self-contained subcommands ---


def _isolate_config(monkeypatch):
    """Neutralize ambient config files + env so config show is deterministic."""
    import junior.cli.settings_builder as sb
    import junior.config as cfg

    # config.* feeds the values (load_configs); settings_builder.* feeds the
    # header source line (used_config_files) — both import the finders by name.
    for mod in (cfg, sb):
        monkeypatch.setattr(mod, "find_global_config", lambda: None)
        monkeypatch.setattr(mod, "find_local_config", lambda: None)
    for var in ("HARNESS", "RUNBOOK", "BACKEND", "MODEL", "PUBLISH"):
        monkeypatch.delenv(var, raising=False)


def test_config_show_reflects_effective_setup(monkeypatch):
    import yaml

    _isolate_config(monkeypatch)
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    parsed = yaml.safe_load(result.stdout)  # header is comments → still valid YAML
    # effective shorthands (defaults when no config is present)
    assert parsed["runbook"] == ""  # no implicit default — must be chosen explicitly
    assert parsed["harness"] == "claudecode"
    assert parsed["publish"] is False
    # with no runbook configured, its specific fields are hidden (nothing to introspect)
    assert "source" not in (parsed.get("context") or {})
    assert parsed["output"]["record"] is True
    # status header present (labels padded to a fixed width so values align)
    assert "# harness: claudecode" in result.stdout
    assert "# runbook: (none" in result.stdout
    assert "# source:  defaults (no config file)" in result.stdout


def test_config_show_with_flags_overrides_setup(monkeypatch):
    import yaml

    _isolate_config(monkeypatch)
    result = runner.invoke(
        app, ["config", "show", "--runbook", "gitlab_pr_review", "--harness", "pydantic"]
    )
    assert result.exit_code == 0
    parsed = yaml.safe_load(result.stdout)
    assert parsed["runbook"] == "gitlab_pr_review"
    assert parsed["harness"] == "pydantic"
    # code-review runbook fields + gitlab + pydantic specifics appear
    assert parsed["context"]["source"] == "auto"
    assert parsed["output"]["ci_server_url"] == "https://gitlab.com"  # gitlab-specific
    assert parsed["llm"]["max_tokens_per_agent"] == 0  # pydantic-specific
    # secrets / tokens never appear in the config body (header comments may name
    # the env var a `not ready` hint refers to — that's not a leaked value).
    flat = yaml.dump(parsed).lower()
    for secret in ("api_key", "gitlab_token", "github_token", "ci_project_id"):
        assert secret not in flat


def test_config_env_platform_runbook_lists_tokens():
    result = runner.invoke(
        app, ["config", "env", "--harness", "pydantic", "--runbook", "github_pr_review"]
    )
    assert result.exit_code == 0
    out = result.stdout
    assert "GITHUB_TOKEN" in out
    assert "OPENAI_API_KEY" in out
    assert "required" in out


def test_config_env_local_review_needs_nothing():
    result = runner.invoke(
        app, ["config", "env", "--harness", "claudecode", "--runbook", "local_review"]
    )
    assert result.exit_code == 0
    assert "no env vars needed" in result.stdout
    assert "claude" in result.stdout  # the CLI-auth note


def test_config_path_prints_global_and_local():
    result = runner.invoke(app, ["config", "path"])
    assert result.exit_code == 0
    assert "global" in result.stdout
    assert "local" in result.stdout


def _fake_tty(monkeypatch):
    """CliRunner's stdin is not a TTY; pretend it is so wizards proceed."""
    import junior.cli.actions as actions

    monkeypatch.setattr(actions, "ensure_interactive_tty", lambda what: None)


def test_init_invokes_wizard(monkeypatch):
    """`junior init` should call interactive_setup, not run the runbook."""
    called: dict[str, bool] = {"called": False}

    def fake_setup() -> None:
        called["called"] = True

    import junior.init_config

    monkeypatch.setattr(junior.init_config, "interactive_setup", fake_setup)
    _fake_tty(monkeypatch)

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0
    assert called["called"] is True


def test_config_init_is_canonical_and_init_is_alias(monkeypatch):
    """`junior config init` and `junior init` both drive the same wizard."""
    calls: list[str] = []

    import junior.init_config

    monkeypatch.setattr(
        junior.init_config, "interactive_setup", lambda: calls.append("setup")
    )
    _fake_tty(monkeypatch)

    assert runner.invoke(app, ["config", "init"]).exit_code == 0
    assert runner.invoke(app, ["init"]).exit_code == 0
    assert calls == ["setup", "setup"]


def test_init_without_tty_exits_cleanly():
    """No terminal → a one-line error and exit 2, not a questionary traceback."""
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 2
    err = result.stderr
    assert "needs a terminal" in err
    assert "Traceback" not in err


def test_run_interactive_without_tty_exits_cleanly(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["run", "-i", "--project-dir", str(tmp_path)])
    assert result.exit_code == 2
    assert "needs a terminal" in result.stderr
    assert "Traceback" not in result.stderr


# --- list (discovery surface) ---


def test_list_shows_runbooks_and_harnesses():
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    out = result.stdout
    assert "Runbooks" in out and "Harnesses" in out
    for name in ("local_review", "github_pr_review", "gitlab_pr_review"):
        assert name in out
    for name in ("claudecode", "codex", "pydantic", "deepagents"):
        assert name in out
    assert "configured default" in out  # the `*` footer


def test_list_runbooks_filter_omits_harnesses():
    result = runner.invoke(app, ["list", "runbooks"])
    assert result.exit_code == 0
    assert "Runbooks" in result.stdout
    assert "Harnesses" not in result.stdout


def test_list_harnesses_filter_omits_runbooks():
    result = runner.invoke(app, ["list", "harnesses"])
    assert result.exit_code == 0
    assert "Harnesses" in result.stdout
    assert "Runbooks" not in result.stdout


def test_list_unknown_target_errors():
    result = runner.invoke(app, ["list", "frobnicate"])
    assert result.exit_code == 2


def test_config_list_is_canonical_and_list_is_alias():
    """`junior config list` and the top-level `junior list` print the same thing."""
    canonical = runner.invoke(app, ["config", "list", "harnesses"])
    alias = runner.invoke(app, ["list", "harnesses"])
    assert canonical.exit_code == 0 and alias.exit_code == 0
    assert "Harnesses" in canonical.stdout
    # both list the same harness names
    for name in ("claudecode", "codex", "pydantic", "deepagents"):
        assert name in canonical.stdout and name in alias.stdout


def test_list_harnesses_shows_install_state():
    result = runner.invoke(app, ["list", "harnesses"])
    assert result.exit_code == 0
    assert "installed" in result.stdout  # install state (not just "ready")


def test_harness_is_ready_reflects_env(monkeypatch):
    """is_ready is an env/CLI self-check the harness implements (no heavy import)."""
    from junior.harnesses.pydantic import HARNESS

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert HARNESS.is_ready().startswith("not ready")

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert HARNESS.is_ready() == "ready"


def test_deepagents_import_stays_lazy():
    """Importing the harness module must NOT pull LangChain (kept lazy for `list`)."""
    import subprocess
    import sys

    code = (
        "import sys, junior.harnesses.deepagents; "
        "sys.exit(1 if 'langchain_core' in sys.modules else 0)"
    )
    assert subprocess.run([sys.executable, "-c", code]).returncode == 0


# --- KV parser via Typer ---


def test_run_rejects_malformed_context(tmp_path):
    """--context without `=` should fail before any runbook work."""
    # The error happens in `run`, in our parser, before settings build.
    result = runner.invoke(app, ["run", "--context", "no_equals_sign", "--project-dir", str(tmp_path)])
    # exit_code is non-zero (Typer maps BadParameter to UsageError).
    assert result.exit_code != 0


# --- Global --config flag flows into commands ---


def test_run_accepts_global_config_flag(tmp_path):
    """Passing --config to the callback wires it into the subcommand's build_settings.

    Smoke check: a nonexistent path produces a clear config error from load_json_configs.
    """
    result = runner.invoke(
        app, ["--config", str(tmp_path / "nope.json"), "run"]
    )
    assert result.exit_code == 2
    assert "Config file not found" in (result.stdout + result.stderr)


# --- End-to-end runbook (collect → review → publish) with mocks ---


def _make_git_repo(path) -> None:
    """Create a `.git/` placeholder so junior's project_dir precheck passes.

    These tests mock `collect`, so we don't need a real repo — just the marker.
    """
    (path / ".git").mkdir(exist_ok=True)


def _fake_context() -> CollectedContext:
    return CollectedContext(
        mr_title="feat: add hello",
        source_branch="feature/hello",
        target_branch="main",
        commit_messages=["Add hello"],
        full_diff="diff --git a/hello.py b/hello.py\n+def hello(): pass\n",
        changed_files=[
            ChangedFile(
                path="hello.py",
                status=FileStatus.ADDED,
                diff="+def hello(): pass\n",
                content="def hello(): pass\n",
            )
        ],
    )


def _fake_llm_output():
    from junior.models import LLMReviewOutput

    return LLMReviewOutput(
        summary="Looks clean.",
        recommendation=Recommendation.COMMENT,
        comments=[],
    )


def _patch_engine(monkeypatch, complete_fn):
    """Replace registry.get_harness with a fake engine driving `complete_fn`."""
    import junior.runbook.registry as registry

    class _FakeEngine:
        file_access = True

        def complete(self, **kwargs):
            return complete_fn(**kwargs)

    monkeypatch.setattr(registry, "get_harness", lambda backend: _FakeEngine())


def test_run_default_emits_raw_json_no_publish(monkeypatch, tmp_path):
    """`junior run <dir>` (no --publish): collect → review → raw JSON to stdout.

    The runbook's publish (post_review) must NOT run without --publish.
    """
    _make_git_repo(tmp_path)
    import junior.collect.local
    import junior.publish.local
    from junior.runbook.base import LLMResult, Usage

    calls: list[str] = []

    def fake_collect(settings):
        calls.append("collect")
        assert settings.context.project_dir == tmp_path
        return _fake_context()

    def fake_complete(*, system_prompt, user_message, output_schema, settings):
        calls.append("review")
        assert "feat: add hello" in user_message
        assert "Check security" in system_prompt, (
            "CLI --prompt should flow through to the engine system prompt"
        )
        return LLMResult(output=_fake_llm_output(), usage=Usage(total_tokens=100))

    monkeypatch.setattr(junior.collect.local, "collect", fake_collect)
    monkeypatch.setattr(
        junior.publish.local, "post_review",
        lambda s, r: calls.append("publish-local"),  # must NOT be called
    )
    _patch_engine(monkeypatch, fake_complete)

    result = runner.invoke(
        app,
        ["run", "--runbook", "local_review", "--harness", "claudecode", "--prompt", "Check security", "--project-dir", str(tmp_path)],
    )

    assert result.exit_code == 0, result.stdout + result.stderr
    assert calls == ["collect", "review"]            # no publish without --publish
    assert '"summary"' in result.stdout              # raw JSON emitted
    assert "Looks clean." in result.stdout


def _write_record(tmp_path, name: str, **overrides) -> None:
    import json

    rec = {
        "timestamp": "2026-06-10T12:00:00",
        "runbook": "local_review",
        "harness": "codex",
        "source": "auto",
        "publish": False,
        "usage": {"total_tokens": 123},
        "errors": [],
        "blocking": False,
        "summary": {"findings": 2, "recommendation": "comment"},
        "output": {"summary": "ok"},
    }
    rec.update(overrides)
    out = tmp_path / ".junior" / "output"
    out.mkdir(parents=True, exist_ok=True)
    (out / name).write_text(json.dumps(rec), encoding="utf-8")


def test_runs_lists_records_newest_first(tmp_path):
    _write_record(tmp_path, "2026-06-09T10-00-00-000000.json", harness="claudecode")
    _write_record(tmp_path, "2026-06-10T12-00-00-000000.json", blocking=True)

    # wide terminal so the rich table doesn't wrap cell contents mid-token
    result = runner.invoke(app, ["runs", "list", str(tmp_path)], env={"COLUMNS": "200"})

    assert result.exit_code == 0, result.stdout + result.stderr
    assert "local_review" in result.stdout
    assert "codex" in result.stdout and "claudecode" in result.stdout
    assert "findings=2" in result.stdout


def test_runs_last_prints_newest_record_json(tmp_path):
    _write_record(tmp_path, "2026-06-09T10-00-00-000000.json", harness="old")
    _write_record(tmp_path, "2026-06-10T12-00-00-000000.json", harness="new")

    result = runner.invoke(app, ["runs", "last", str(tmp_path)])

    assert result.exit_code == 0, result.stdout + result.stderr
    assert '"new"' in result.stdout and '"old"' not in result.stdout


def test_runs_empty_dir_errors(tmp_path):
    result = runner.invoke(app, ["runs", str(tmp_path)])
    assert result.exit_code == 2
    assert "no run records" in (result.stdout + result.stderr)


def test_runs_unknown_target_errors(tmp_path):
    result = runner.invoke(app, ["runs", "bogus", str(tmp_path)])
    assert result.exit_code == 2


def test_run_raw_output_hints_publish_on_tty_only(monkeypatch, tmp_path):
    """Raw stdout output adds a stderr --publish hint for humans (TTY), and
    stays hint-free in pipes/CI. The stdout bytes are identical either way."""
    _make_git_repo(tmp_path)
    import junior.cli.actions as actions
    import junior.collect.local
    from junior.runbook.base import LLMResult, Usage

    monkeypatch.setattr(junior.collect.local, "collect", lambda s: _fake_context())
    _patch_engine(
        monkeypatch,
        lambda **kw: LLMResult(output=_fake_llm_output(), usage=Usage()),
    )

    args = ["run", "--runbook", "local_review", "--harness", "claudecode", "--project-dir", str(tmp_path)]

    result = runner.invoke(app, args)  # CliRunner stdout is not a TTY
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "Hint" not in result.stderr

    monkeypatch.setattr(actions, "_stdout_is_tty", lambda: True)
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "--publish" in result.stderr
    assert '"summary"' in result.stdout


def test_run_output_dash_forces_stdout_over_config(monkeypatch, tmp_path):
    """`-o -` resets a config-provided output_file back to stdout."""
    _make_git_repo(tmp_path)
    import junior.collect.local
    from junior.runbook.base import LLMResult, Usage

    monkeypatch.setattr(junior.collect.local, "collect", lambda s: _fake_context())
    _patch_engine(
        monkeypatch,
        lambda **kw: LLMResult(output=_fake_llm_output(), usage=Usage()),
    )

    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(f"output_file: {tmp_path / 'review.md'}\n")

    result = runner.invoke(
        app,
        ["--config", str(cfg), "run", "--runbook", "local_review", "--harness", "claudecode", "-o", "-", "--project-dir", str(tmp_path)],
    )

    assert result.exit_code == 0, result.stdout + result.stderr
    assert '"summary"' in result.stdout                  # raw JSON on stdout
    assert not (tmp_path / "review.md").exists()         # config file sink overridden


def test_run_output_file_directory_fails_before_review(monkeypatch, tmp_path):
    """`-o <dir>` (including `-o ""`, which is Path('.')) fails in preflight,
    before collect/review — not with a traceback after the paid LLM call."""
    _make_git_repo(tmp_path)
    import junior.collect.local

    calls: list[str] = []
    monkeypatch.setattr(
        junior.collect.local, "collect",
        lambda s: calls.append("collect") or _fake_context(),
    )

    for bad in (str(tmp_path), ""):
        result = runner.invoke(
            app, ["run", "--runbook", "local_review", "--harness", "claudecode", "-o", bad, "--project-dir", str(tmp_path)]
        )
        assert result.exit_code == 2, result.stdout + result.stderr
        assert "directory" in (result.stdout + result.stderr)
    assert calls == []


def test_dry_run_rejects_dash_output(tmp_path):
    """dry-run's -o saves the context file; '-' is a run-only convention."""
    _make_git_repo(tmp_path)
    result = runner.invoke(app, ["dry-run", "--runbook", "local_review", "-o", "-", "--project-dir", str(tmp_path)])
    assert result.exit_code == 2, result.stdout + result.stderr


def test_run_publish_flag_calls_platform_only(monkeypatch, tmp_path):
    """`--publish` on a platform runbook runs its custom publish (posts), and the
    raw JSON is NOT printed to stdout."""
    _make_git_repo(tmp_path)
    import junior.collect.gitlab
    import junior.publish.gitlab
    import junior.publish.local
    from junior.runbook.base import LLMResult, Usage

    calls: list[str] = []

    monkeypatch.setattr(junior.collect.gitlab, "collect", lambda settings: _fake_context())
    _patch_engine(
        monkeypatch,
        lambda **kw: LLMResult(output=_fake_llm_output(), usage=Usage(total_tokens=1)),
    )
    monkeypatch.setattr(
        junior.publish.local, "post_review", lambda s, r: calls.append("publish-local")
    )
    monkeypatch.setattr(
        junior.publish.gitlab, "post_review", lambda s, r: calls.append("publish-platform")
    )

    result = runner.invoke(
        app,
        ["run", "--runbook", "gitlab_pr_review", "--harness", "claudecode", "--publish", "--project-dir", str(tmp_path)],
        env={
            "GITLAB_TOKEN": "glpat-test",
            "CI_PROJECT_ID": "1",
            "CI_MERGE_REQUEST_IID": "1",
        },
    )

    assert result.exit_code == 0, result.stdout + result.stderr
    assert calls == ["publish-platform"]             # platform post only, no local print
    assert '"summary"' not in result.stdout          # raw output hidden when publishing


def test_run_writes_run_record(monkeypatch, tmp_path):
    """A successful run drops a JSON record under <project_dir>/.junior/output/."""
    _make_git_repo(tmp_path)
    import junior.collect.local
    import junior.publish.local
    from junior.runbook.base import LLMResult, Usage

    monkeypatch.setattr(junior.collect.local, "collect", lambda s: _fake_context())
    monkeypatch.setattr(junior.publish.local, "post_review", lambda s, r: None)
    _patch_engine(
        monkeypatch,
        lambda **kw: LLMResult(output=_fake_llm_output(), usage=Usage(total_tokens=42)),
    )

    result = runner.invoke(app, ["run", "--runbook", "local_review", "--harness", "claudecode", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0, result.stdout + result.stderr

    records = list((tmp_path / ".junior" / "output").glob("*.json"))
    assert len(records) == 1, "exactly one run record should be written"

    import json

    data = json.loads(records[0].read_text())
    assert data["runbook"] == "local_review"
    assert data["harness"] == "claudecode"
    assert data["usage"]["total_tokens"] == 42
    assert data["output"]["summary"] == "Looks clean."


def test_run_no_record_flag_skips_record(monkeypatch, tmp_path):
    """`--no-record` suppresses the .junior/output JSON."""
    _make_git_repo(tmp_path)
    import junior.collect.local
    import junior.publish.local
    from junior.runbook.base import LLMResult, Usage

    monkeypatch.setattr(junior.collect.local, "collect", lambda s: _fake_context())
    monkeypatch.setattr(junior.publish.local, "post_review", lambda s, r: None)
    _patch_engine(
        monkeypatch,
        lambda **kw: LLMResult(output=_fake_llm_output(), usage=Usage(total_tokens=1)),
    )

    result = runner.invoke(
        app, ["run", "--runbook", "local_review", "--harness", "claudecode", "--no-record", "--project-dir", str(tmp_path)]
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert not (tmp_path / ".junior").exists()


def test_config_flag_after_subcommand_is_honored(monkeypatch, tmp_path):
    """`--config FILE` works *after* the subcommand, not only before it (it used
    to be a parent-callback-only option — a positional foot-gun)."""
    _make_git_repo(tmp_path)
    import junior.collect.local

    monkeypatch.setattr(junior.collect.local, "collect", lambda s: _fake_context())
    cfg = tmp_path / "j.yaml"
    cfg.write_text("runbook: local_review\nharness: claudecode\nmodel: zzz-unique-model\n")

    result = runner.invoke(
        app, ["dry-run", "--config", str(cfg), "--project-dir", str(tmp_path)]
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "zzz-unique-model" in result.stdout  # value came from the post-command --config


def test_config_flag_nearest_command_wins(monkeypatch, tmp_path):
    """Both positions given → the one nearest the command wins (single effective
    config), so `junior --config A dry-run --config B` uses B."""
    _make_git_repo(tmp_path)
    import junior.collect.local

    monkeypatch.setattr(junior.collect.local, "collect", lambda s: _fake_context())
    a = tmp_path / "a.yaml"
    a.write_text("model: from-A-global\n")
    b = tmp_path / "b.yaml"
    b.write_text("runbook: local_review\nharness: claudecode\nmodel: from-B-local\n")

    result = runner.invoke(
        app,
        ["--config", str(a), "dry-run", "--config", str(b), "--project-dir", str(tmp_path)],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "from-B-local" in result.stdout
    assert "from-A-global" not in result.stdout


def test_run_from_file_skips_collect(monkeypatch, tmp_path):
    """`--from-file ctx.json` should not call collect — context is read from disk."""
    import junior.collect.local
    import junior.publish.local
    from junior.runbook.base import LLMResult, Usage

    ctx_path = tmp_path / "ctx.json"
    ctx_path.write_text(_fake_context().model_dump_json(), encoding="utf-8")

    def boom(*_a, **_kw):
        raise AssertionError("collect must not be called when --from-file is used")

    review_called: list[bool] = []
    monkeypatch.setattr(junior.collect.local, "collect", boom)

    def fake_complete(**kw):
        review_called.append(True)
        return LLMResult(output=_fake_llm_output(), usage=Usage(total_tokens=1))

    _patch_engine(monkeypatch, fake_complete)
    monkeypatch.setattr(junior.publish.local, "post_review", lambda s, r: None)

    result = runner.invoke(
        app,
        ["run", "--runbook", "local_review", "--from-file", str(ctx_path), "--harness", "claudecode", "--project-dir", str(tmp_path)],
    )

    assert result.exit_code == 0, result.stdout + result.stderr
    assert review_called == [True]


def test_run_publish_file_skips_collect_and_review(monkeypatch, tmp_path):
    """`--publish-file out.md` skips collect+review; posts the .md via the runbook."""
    import junior.collect.gitlab
    import junior.publish.gitlab

    review_md = tmp_path / "review.md"
    review_md.write_text("# review\n\nBody.", encoding="utf-8")

    def boom(*_a, **_kw):
        raise AssertionError("collect must not run when --publish-file is used")

    posted: dict = {}

    def fake_post(settings, result):
        posted["pre_formatted"] = result.pre_formatted

    monkeypatch.setattr(junior.collect.gitlab, "collect", boom)
    monkeypatch.setattr(junior.publish.gitlab, "post_review", fake_post)

    result = runner.invoke(
        app,
        ["run", "--runbook", "gitlab_pr_review", "--publish-file", str(review_md), "--project-dir", str(tmp_path)],
        env={
            "GITLAB_TOKEN": "glpat-test",
            "CI_PROJECT_ID": "1",
            "CI_MERGE_REQUEST_IID": "1",
        },
    )

    assert result.exit_code == 0, result.stdout + result.stderr
    assert posted["pre_formatted"] == "# review\n\nBody."


def test_run_blocking_review_returns_exit_code_1(monkeypatch, tmp_path):
    """Critical findings should fail the runbook (exit 1) after publishing the review."""
    _make_git_repo(tmp_path)
    import junior.collect.local
    import junior.publish.local
    from junior.models import LLMReviewOutput, ReviewComment, ReviewCategory, Severity
    from junior.runbook.base import LLMResult, Usage

    blocking = LLMReviewOutput(
        summary="Found a critical bug.",
        recommendation=Recommendation.REQUEST_CHANGES,
        comments=[
            ReviewComment(
                category=ReviewCategory.SECURITY,
                severity=Severity.CRITICAL,
                message="SQL injection",
            )
        ],
    )

    monkeypatch.setattr(junior.collect.local, "collect", lambda s: _fake_context())
    _patch_engine(monkeypatch, lambda **kw: LLMResult(output=blocking, usage=Usage(total_tokens=1)))
    monkeypatch.setattr(junior.publish.local, "post_review", lambda s, r: None)

    result = runner.invoke(app, ["run", "--runbook", "local_review", "--harness", "claudecode", "--project-dir", str(tmp_path)])

    assert result.exit_code == 1, result.stdout + result.stderr


def test_run_no_changes_exits_cleanly(monkeypatch, tmp_path):
    """Empty diff should short-circuit with exit 0 — no review call."""
    _make_git_repo(tmp_path)
    import junior.collect.local
    import junior.publish.local

    empty_ctx = CollectedContext(target_branch="main", full_diff="")

    def boom(**_kw):
        raise AssertionError("engine must not be called when diff is empty")

    monkeypatch.setattr(junior.collect.local, "collect", lambda s: empty_ctx)
    _patch_engine(monkeypatch, boom)
    monkeypatch.setattr(junior.publish.local, "post_review", lambda s, r: None)

    result = runner.invoke(app, ["run", "--runbook", "local_review", "--harness", "claudecode", "--project-dir", str(tmp_path)])

    assert result.exit_code == 0, result.stdout + result.stderr


def test_dry_run_saves_context_without_review(monkeypatch, tmp_path):
    """`junior dry-run -o ctx.json` saves what collect() returns and never calls the harness."""
    _make_git_repo(tmp_path)
    import junior.collect.local

    out = tmp_path / "ctx.json"

    monkeypatch.setattr(junior.collect.local, "collect", lambda s: _fake_context())

    def boom(**_kw):
        raise AssertionError("harness must not run from `junior dry-run`")

    _patch_engine(monkeypatch, boom)

    result = runner.invoke(app, ["dry-run", "--runbook", "local_review", "-o", str(out), "--project-dir", str(tmp_path)])

    assert result.exit_code == 0, result.stdout + result.stderr
    assert out.exists()
    saved = CollectedContext.model_validate_json(out.read_text())
    assert saved.mr_title == "feat: add hello"
    # the preview shows the plan + what the harness would receive
    assert "local_review" in result.stdout
    assert "feat: add hello" in result.stdout  # user message echoed in preview
