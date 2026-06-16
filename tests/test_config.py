"""Tests for Settings — three nested groups (Context, Review, Output) + preflight.

Target shape:
    Settings
      .context: ContextSettings   — what to review (source, prompts, MR meta)
      .llm:  LLMSettings    — how to call the model (harness, model, keys, limits)
      .output:  OutputSettings    — where to send (tokens, file, CI publish vars)
      .log_level: LogLevel
      .preflight(review, publish) -> list[str]
"""

import yaml

import pytest
from pydantic import ValidationError

from junior import config as config_module
from junior.config import (
    ClaudeCodeSettings,
    HarnessKind,
    ContextSettings,
    LogLevel,
    OutputSettings,
    LLMSettings,
    Settings,
    SourceMode,
)


@pytest.fixture(autouse=True)
def _isolate_config_discovery(monkeypatch):
    """Neutralize real ~/.config and project .junior.* so config tests are hermetic.

    Tests that inject a config re-set GLOBAL_CONFIG_CANDIDATES themselves.
    """
    monkeypatch.setattr(config_module, "GLOBAL_CONFIG_CANDIDATES", ())
    monkeypatch.setattr(config_module, "LOCAL_CONFIG_CANDIDATES", ())


# ---------------------------------------------------------------------------
# ContextSettings — what to review
# ---------------------------------------------------------------------------


class TestContextSettings:
    def test_defaults(self):
        s = ContextSettings()
        assert s.source == SourceMode.AUTO
        assert s.prompts == []
        assert s.target_branch == "main"
        assert s.context == {}
        assert s.context_files == {}

    def test_source_enum_validation(self):
        with pytest.raises(ValidationError):
            ContextSettings(source="invalid-mode")

    def test_source_lowercase_accepted(self):
        s = ContextSettings(source="staged")
        assert s.source == SourceMode.STAGED

    def test_target_branch_from_ci_alias(self, monkeypatch):
        monkeypatch.setenv("CI_MERGE_REQUEST_TARGET_BRANCH_NAME", "develop")
        s = ContextSettings()
        assert s.target_branch == "develop"

    def test_mr_metadata_from_ci_aliases(self, monkeypatch):
        monkeypatch.setenv("CI_MERGE_REQUEST_TITLE", "Feature X")
        monkeypatch.setenv("CI_MERGE_REQUEST_DESCRIPTION", "Long description")
        monkeypatch.setenv("CI_MERGE_REQUEST_SOURCE_BRANCH_NAME", "feat/x")
        s = ContextSettings()
        assert s.mr_title == "Feature X"
        assert s.mr_description == "Long description"
        assert s.source_branch == "feat/x"

    def test_project_dir_resolved_to_absolute(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        s = ContextSettings(project_dir=".")
        assert s.project_dir.is_absolute()

    def test_base_sha_overrides_ci_var(self, monkeypatch):
        monkeypatch.setenv("CI_MERGE_REQUEST_DIFF_BASE_SHA", "ci-sha")
        s = ContextSettings(base_sha="cli-sha")
        assert s.base_sha == "cli-sha"


# ---------------------------------------------------------------------------
# LLMSettings — how to review
# ---------------------------------------------------------------------------


class TestLLMSettings:
    def test_defaults(self):
        s = LLMSettings()
        assert s.harness == HarnessKind.CLAUDECODE
        assert s.model == ""
        assert s.openai_api_key is None
        assert s.anthropic_api_key is None
        assert s.max_tokens_per_agent == 0
        assert s.max_file_size == 100_000
        # dead knobs were removed
        assert not hasattr(s, "temperature")
        assert not hasattr(s, "max_concurrent_agents")

    def test_harness_via_env(self, monkeypatch):
        monkeypatch.setenv("HARNESS", "pydantic")
        s = LLMSettings()
        assert s.harness == HarnessKind.PYDANTIC

    def test_backend_alias_via_env(self, monkeypatch):
        """Deprecated `BACKEND` env still maps to `harness` (kept one version)."""
        monkeypatch.delenv("HARNESS", raising=False)
        monkeypatch.setenv("BACKEND", "pydantic")
        assert LLMSettings().harness == HarnessKind.PYDANTIC

    def test_backend_alias_via_kwarg(self):
        """Deprecated `backend=` kwarg/config key still maps to `harness`."""
        assert LLMSettings(backend="codex").harness == HarnessKind.CODEX

    def test_model_explicit_provider_prefix(self):
        s = LLMSettings(model="anthropic:claude-opus-4-6")
        assert s.resolved_provider == "anthropic"
        assert s.resolved_model == "claude-opus-4-6"
        assert s.model_string == "anthropic:claude-opus-4-6"

    def test_model_without_prefix_uses_api_key_for_provider(self):
        s = LLMSettings(model="gpt-4o", openai_api_key="sk-xxx")
        assert s.resolved_provider == "openai"
        assert s.resolved_model == "gpt-4o"
        assert s.model_string == "openai:gpt-4o"

    def test_model_empty_uses_default_for_resolved_provider(self):
        s = LLMSettings(anthropic_api_key="sk-ant-xxx")
        assert s.resolved_provider == "anthropic"
        assert s.resolved_model.startswith("claude-")

    def test_invalid_provider_prefix_raises(self):
        with pytest.raises(ValidationError, match="provider"):
            LLMSettings(model="deepmind:gemini-pro")

    def test_resolved_provider_empty_without_key(self):
        s = LLMSettings()
        assert s.resolved_provider == ""
        assert s.resolved_model == ""

    def test_display_model_pydantic_uses_resolved(self):
        s = LLMSettings(harness=HarnessKind.PYDANTIC, openai_api_key="sk-xxx")
        assert s.display_model == "gpt-5.4-mini"

    def test_display_model_claudecode_requires_explicit(self):
        assert LLMSettings(harness=HarnessKind.CLAUDECODE).display_model == ""
        assert (
            LLMSettings(
                harness=HarnessKind.CLAUDECODE, model="claude-sonnet-4-6"
            ).display_model
            == "claude-sonnet-4-6"
        )

    def test_display_model_codex_hidden(self):
        s = LLMSettings(harness=HarnessKind.CODEX, model="anything")
        assert s.display_model == ""

    def test_display_model_pi_shows_raw_when_set(self):
        # pi passes --model through verbatim (provider/id), so surface it as-is
        assert LLMSettings(harness=HarnessKind.PI, model="ollama/qwen3").display_model == "ollama/qwen3"
        assert LLMSettings(harness=HarnessKind.PI).display_model == ""


# ---------------------------------------------------------------------------
# ClaudeCodeSettings — claudecode-only knobs (llm.claudecode)
# ---------------------------------------------------------------------------


class TestClaudeCodeSettings:
    def test_default_permission_mode(self):
        assert ClaudeCodeSettings().permission_mode == "bypassPermissions"
        # nested default is wired into LLMSettings
        assert LLMSettings().claudecode.permission_mode == "bypassPermissions"

    def test_valid_permission_mode_accepted(self):
        assert ClaudeCodeSettings(permission_mode="acceptEdits").permission_mode == "acceptEdits"

    def test_invalid_permission_mode_raises(self):
        with pytest.raises(ValidationError, match="unknown permission_mode"):
            ClaudeCodeSettings(permission_mode="yolo")

    def test_nested_dict_via_llm_settings(self):
        s = LLMSettings(claudecode={"permission_mode": "plan"})
        assert s.claudecode.permission_mode == "plan"

    def test_read_from_yaml_config(self, tmp_path, monkeypatch):
        path = tmp_path / "config.yaml"
        path.write_text(
            yaml.safe_dump({"llm": {"claudecode": {"permission_mode": "acceptEdits"}}})
        )
        monkeypatch.setattr(config_module, "GLOBAL_CONFIG_CANDIDATES", (path,))
        loaded = config_module.load_configs()
        s = Settings(**loaded)
        assert s.llm.claudecode.permission_mode == "acceptEdits"


# ---------------------------------------------------------------------------
# OutputSettings — where to send
# ---------------------------------------------------------------------------


class TestOutputSettings:
    def test_defaults(self):
        s = OutputSettings()
        assert s.output_file == ""
        assert s.publish is False
        assert s.gitlab_token == ""
        assert s.github_token == ""
        assert s.ci_server_url == "https://gitlab.com"

    def test_gitlab_ci_aliases(self, monkeypatch):
        monkeypatch.setenv("CI_PROJECT_ID", "42")
        monkeypatch.setenv("CI_MERGE_REQUEST_IID", "7")
        monkeypatch.setenv("CI_COMMIT_SHA", "abc")
        s = OutputSettings()
        assert s.ci_project_id == 42
        assert s.ci_merge_request_iid == 7
        assert s.ci_commit_sha == "abc"

    def test_github_aliases(self, monkeypatch):
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
        monkeypatch.setenv("GITHUB_EVENT_NUMBER", "123")
        s = OutputSettings()
        assert s.github_repository == "owner/repo"
        assert s.github_event_number == 123


# ---------------------------------------------------------------------------
# Settings composition
# ---------------------------------------------------------------------------


class TestSettingsComposition:
    def test_groups_are_present(self):
        s = Settings()
        assert isinstance(s.context, ContextSettings)
        assert isinstance(s.llm, LLMSettings)
        assert isinstance(s.output, OutputSettings)
        assert s.log_level == LogLevel.INFO

    def test_each_group_loads_env(self, monkeypatch):
        monkeypatch.setenv("SOURCE", "staged")
        monkeypatch.setenv("BACKEND", "pydantic")
        monkeypatch.setenv("OUTPUT_FILE", "/tmp/review.md")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-xxx")
        s = Settings()
        assert s.context.source == SourceMode.STAGED
        assert s.llm.harness == HarnessKind.PYDANTIC
        assert s.llm.openai_api_key == "sk-xxx"
        assert s.output.output_file == "/tmp/review.md"

    def test_explicit_group_override(self):
        s = Settings(
            llm=LLMSettings(harness=HarnessKind.CODEX),
            output=OutputSettings(gitlab_token="glpat-xxx"),
        )
        assert s.llm.harness == HarnessKind.CODEX
        assert s.output.gitlab_token == "glpat-xxx"

    def test_dict_payload_for_group(self):
        """Passing a dict to a group field should work (covers nested JSON load)."""
        s = Settings(
            context={"prompts": ["Check security"]},
            llm={"harness": "pydantic", "openai_api_key": "sk-xxx"},
        )
        assert s.context.prompts == ["Check security"]
        assert s.llm.harness == HarnessKind.PYDANTIC


class TestLogLevelEnum:
    def test_valid_levels(self):
        for level in ("DEBUG", "INFO", "WARNING", "ERROR"):
            s = Settings(log_level=level)
            assert s.log_level.value == level

    def test_lowercase_normalized(self):
        s = Settings(log_level="debug")
        assert s.log_level == LogLevel.DEBUG

    def test_invalid_raises(self):
        with pytest.raises(ValidationError):
            Settings(log_level="VERBOSE")


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------


class TestPreflightReview:
    def test_pydantic_without_key_fails(self):
        s = Settings(llm=LLMSettings(harness=HarnessKind.PYDANTIC))
        errors = s.preflight(review=True)
        assert any("API key" in e or "provider" in e.lower() for e in errors)

    def test_pydantic_with_key_ok(self):
        s = Settings(
            llm=LLMSettings(
                harness=HarnessKind.PYDANTIC, openai_api_key="sk-xxx"
            )
        )
        errors = s.preflight(review=True)
        assert errors == []

    def test_claudecode_skips_check(self):
        s = Settings(llm=LLMSettings(harness=HarnessKind.CLAUDECODE))
        errors = s.preflight(review=True)
        assert errors == []

    def test_codex_skips_check(self):
        s = Settings(llm=LLMSettings(harness=HarnessKind.CODEX))
        errors = s.preflight(review=True)
        assert errors == []

    def test_review_false_skips_check(self):
        s = Settings(llm=LLMSettings(harness=HarnessKind.PYDANTIC))
        errors = s.preflight(review=False)
        assert errors == []


class TestPreflightOutputFile:
    """An unwritable -o target must fail before the (paid) LLM call."""

    def test_directory_rejected(self, tmp_path):
        s = Settings(output=OutputSettings(output_file=str(tmp_path)))
        errors = s.preflight(review=False)
        assert any("directory" in e for e in errors)

    def test_empty_string_path_rejected(self):
        # `-o ""` reaches Settings as Path("") == Path(".") — a directory.
        s = Settings(output=OutputSettings(output_file="."))
        errors = s.preflight(review=False)
        assert any("directory" in e for e in errors)

    def test_missing_parent_rejected(self, tmp_path):
        s = Settings(output=OutputSettings(output_file=str(tmp_path / "no" / "out.md")))
        errors = s.preflight(review=False)
        assert any("does not exist" in e for e in errors)

    def test_valid_path_ok(self, tmp_path):
        s = Settings(output=OutputSettings(output_file=str(tmp_path / "out.md")))
        assert s.preflight(review=False) == []

    def test_unset_ok(self):
        s = Settings()
        assert s.preflight(review=False) == []


class TestRunbookValidatePublish:
    """Publish requirements now live in each platform runbook's validate()."""

    def _gitlab(self):
        from junior.runbooks.code_review.gitlab import GitlabPrReview

        return GitlabPrReview()

    def _github(self):
        from junior.runbooks.code_review.github import GithubPrReview

        return GithubPrReview()

    def _local(self):
        from junior.runbooks.code_review.local import LocalReview

        return LocalReview()

    def test_no_publish_no_errors(self):
        assert self._github().validate(Settings(), publish_enabled=False) == []

    def test_local_publish_has_no_requirements(self):
        # local_review now *can* publish (renders Markdown locally) — no tokens needed.
        assert self._local().validate(Settings(), publish_enabled=True) == []

    def test_gitlab_missing_token(self):
        errors = self._gitlab().validate(Settings(), publish_enabled=True)
        assert any("GITLAB_TOKEN" in e for e in errors)

    def test_gitlab_missing_ids(self):
        s = Settings(output=OutputSettings(gitlab_token="glpat-xxx"))
        errors = self._gitlab().validate(s, publish_enabled=True)
        assert any("CI_PROJECT_ID" in e for e in errors)

    def test_gitlab_valid(self):
        s = Settings(
            output=OutputSettings(
                gitlab_token="glpat-xxx", ci_project_id=123, ci_merge_request_iid=42
            )
        )
        assert self._gitlab().validate(s, publish_enabled=True) == []

    def test_github_missing_fields(self):
        s = Settings(output=OutputSettings(github_token="ghp_xxx"))
        errors = self._github().validate(s, publish_enabled=True)
        assert any("GITHUB_REPOSITORY" in e for e in errors)
        assert any("GITHUB_EVENT_NUMBER" in e for e in errors)

    def test_github_valid(self):
        s = Settings(
            output=OutputSettings(
                github_token="ghp_xxx", github_repository="owner/repo", github_event_number=1
            )
        )
        assert self._github().validate(s, publish_enabled=True) == []


class TestPreflightContextFiles:
    def test_missing_file_fails(self):
        s = Settings(
            context=ContextSettings(context_files={"x": "/nonexistent/file"})
        )
        errors = s.preflight(review=False)
        assert any("file not found" in e for e in errors)

    def test_existing_file_ok(self, tmp_path):
        f = tmp_path / "rules.txt"
        f.write_text("be strict")
        s = Settings(
            context=ContextSettings(context_files={"custom": str(f)})
        )
        errors = s.preflight(review=False)
        assert errors == []

    def test_empty_ok(self):
        s = Settings()
        errors = s.preflight(review=False)
        assert errors == []


class TestPreflightCombined:
    def test_multiple_errors_collected(self):
        s = Settings(
            context=ContextSettings(context_files={"x": "/nonexistent"}),
            llm=LLMSettings(harness=HarnessKind.PYDANTIC),
        )
        errors = s.preflight(review=True)
        assert len(errors) >= 2


# ---------------------------------------------------------------------------
# JSON config loading & save (nested format)
# ---------------------------------------------------------------------------


class TestYamlConfigLoading:
    def test_nested_keys_parsed(self, tmp_path, monkeypatch):
        path = tmp_path / "config.yaml"
        path.write_text(
            yaml.safe_dump(
                {
                    "context": {"prompts": ["Check security"]},
                    "llm": {"harness": "pydantic"},
                    "output": {"output_file": "review.md"},
                }
            )
        )
        monkeypatch.setattr(
            config_module, "GLOBAL_CONFIG_CANDIDATES", (path,)
        )
        loaded = config_module.load_configs()
        assert loaded["context"] == {"prompts": ["Check security"]}
        assert loaded["llm"] == {"harness": "pydantic"}
        assert loaded["output"] == {"output_file": "review.md"}

    def test_env_overrides_nested_config_field(self, tmp_path, monkeypatch):
        """env var must win over a config-file group field (env > file)."""
        path = tmp_path / "config.yaml"
        path.write_text(yaml.safe_dump({"llm": {"harness": "codex", "model": "x"}}))
        monkeypatch.setattr(config_module, "GLOBAL_CONFIG_CANDIDATES", (path,))
        monkeypatch.setenv("HARNESS", "pydantic")

        loaded = config_module.load_configs()
        # env-shadowed key dropped from the file config; sibling kept
        assert "harness" not in loaded["llm"]
        assert loaded["llm"]["model"] == "x"
        # env wins; the unrelated config field survives
        s = Settings(**loaded)
        assert s.llm.harness == HarnessKind.PYDANTIC
        assert s.llm.model == "x"

    def test_settings_from_nested_dict(self):
        s = Settings(
            context={"prompts": ["Check security", "Look at logic"]},
            llm={"harness": "pydantic", "openai_api_key": "sk-xxx"},
        )
        assert s.context.prompts == ["Check security", "Look at logic"]
        assert s.llm.harness == HarnessKind.PYDANTIC
        assert s.llm.openai_api_key == "sk-xxx"


class TestFindLocalConfig:
    """`.junior.yaml` discovery: CWD first, then upward to the repo root."""

    def _candidates(self, monkeypatch):
        monkeypatch.setattr(
            config_module, "LOCAL_CONFIG_CANDIDATES", (".junior.yaml", ".junior.yml")
        )

    def test_found_in_cwd(self, tmp_path, monkeypatch):
        self._candidates(monkeypatch)
        (tmp_path / ".junior.yaml").write_text("runbook: local_review\n")
        monkeypatch.chdir(tmp_path)
        assert config_module.find_local_config() == tmp_path / ".junior.yaml"

    def test_walks_up_to_git_root(self, tmp_path, monkeypatch):
        """Running from a subdirectory of the repo sees the root config."""
        self._candidates(monkeypatch)
        (tmp_path / ".git").mkdir()
        (tmp_path / ".junior.yaml").write_text("runbook: local_review\n")
        sub = tmp_path / "src" / "pkg"
        sub.mkdir(parents=True)
        monkeypatch.chdir(sub)
        assert config_module.find_local_config() == tmp_path / ".junior.yaml"

    def test_does_not_cross_repo_boundary(self, tmp_path, monkeypatch):
        """A config *above* the repo root is never picked up."""
        self._candidates(monkeypatch)
        (tmp_path / ".junior.yaml").write_text("runbook: local_review\n")
        repo = tmp_path / "repo"
        (repo / ".git").mkdir(parents=True)
        monkeypatch.chdir(repo)
        assert config_module.find_local_config() is None

    def test_no_walk_outside_a_repo(self, tmp_path, monkeypatch):
        """Without a .git anywhere, only the CWD is checked."""
        self._candidates(monkeypatch)
        (tmp_path / ".junior.yaml").write_text("runbook: local_review\n")
        sub = tmp_path / "sub"
        sub.mkdir()
        monkeypatch.chdir(sub)
        assert config_module.find_local_config() is None

    def test_nested_repo_stops_at_inner_root(self, tmp_path, monkeypatch):
        """A nested repo (e.g. a vendored checkout) does not inherit the outer
        repo's config."""
        self._candidates(monkeypatch)
        (tmp_path / ".git").mkdir()
        (tmp_path / ".junior.yaml").write_text("runbook: local_review\n")
        inner = tmp_path / "vendor" / "other"
        (inner / ".git").mkdir(parents=True)
        monkeypatch.chdir(inner)
        assert config_module.find_local_config() is None


class TestTopLevelShorthands:
    def _load(self, tmp_path, monkeypatch, body: str) -> dict:
        path = tmp_path / "config.yaml"
        path.write_text(body)
        monkeypatch.setattr(config_module, "GLOBAL_CONFIG_CANDIDATES", (path,))
        return config_module.load_configs()

    def test_flat_keys_fold_into_groups(self, tmp_path, monkeypatch):
        loaded = self._load(
            tmp_path, monkeypatch,
            "harness: codex\nmodel: openai:gpt-5\npublish: true\noutput_file: review.md\n",
        )
        assert loaded["llm"] == {"harness": "codex", "model": "openai:gpt-5"}
        assert loaded["output"] == {"publish": True, "output_file": "review.md"}
        # the flat keys are gone (folded down)
        assert "harness" not in loaded and "output_file" not in loaded
        # and Settings accepts the result
        s = Settings(**loaded)
        assert s.llm.harness == HarnessKind.CODEX
        assert s.output.output_file == "review.md"

    def test_both_forms_equivalent(self, tmp_path, monkeypatch):
        flat = self._load(tmp_path, monkeypatch, "harness: codex\n")
        nested = self._load(tmp_path, monkeypatch, "llm:\n  harness: codex\n")
        assert flat == nested == {"llm": {"harness": "codex"}}

    def test_top_level_wins_over_nested_in_same_file(self, tmp_path, monkeypatch):
        loaded = self._load(
            tmp_path, monkeypatch, "harness: codex\nllm:\n  harness: pydantic\n  model: x\n"
        )
        assert loaded["llm"]["harness"] == "codex"  # top-level wins
        assert loaded["llm"]["model"] == "x"  # sibling kept

    def test_env_still_overrides_flat_shorthand(self, tmp_path, monkeypatch):
        path = tmp_path / "config.yaml"
        path.write_text("harness: codex\n")
        monkeypatch.setattr(config_module, "GLOBAL_CONFIG_CANDIDATES", (path,))
        monkeypatch.setenv("HARNESS", "pydantic")
        loaded = config_module.load_configs()
        assert "harness" not in loaded.get("llm", {})  # env-shadowed, dropped
        assert Settings(**loaded).llm.harness == HarnessKind.PYDANTIC


class TestSaveGlobalConfig:
    def _redirect(self, tmp_path, monkeypatch):
        path = tmp_path / "settings.yaml"
        monkeypatch.setattr(config_module, "GLOBAL_CONFIG_DIR", tmp_path)
        monkeypatch.setattr(config_module, "GLOBAL_CONFIG_PATH", path)
        return path

    def test_writes_fresh_flat_file(self, tmp_path, monkeypatch):
        path = self._redirect(tmp_path, monkeypatch)
        config_module.save_global_config({"harness": "pydantic"})
        # shorthand stays flat on disk
        assert yaml.safe_load(path.read_text()) == {"harness": "pydantic"}

    def test_deep_merge_preserves_other_groups(self, tmp_path, monkeypatch):
        path = self._redirect(tmp_path, monkeypatch)
        # existing file in the OLD nested form — save must canonicalise it flat,
        # not leave a stale `llm.harness` beside the new top-level `harness`.
        path.write_text(
            yaml.safe_dump(
                {
                    "llm": {"harness": "claudecode", "max_file_size": 50000},
                    "context": {"prompts": ["Check security"]},
                }
            )
        )
        config_module.save_global_config({"harness": "pydantic", "model": "x"})
        result = yaml.safe_load(path.read_text())
        # shorthand lifted to the root, updated; no nested `harness` left behind
        assert result["harness"] == "pydantic"
        assert result["model"] == "x"
        assert "harness" not in result.get("llm", {})
        # non-shorthand group fields preserved
        assert result["llm"]["max_file_size"] == 50000
        assert result["context"]["prompts"] == ["Check security"]

    def test_recovers_from_corrupt_file(self, tmp_path, monkeypatch):
        path = self._redirect(tmp_path, monkeypatch)
        path.write_text("{ : not: valid: yaml")
        config_module.save_global_config({"harness": "codex"})
        assert yaml.safe_load(path.read_text()) == {"harness": "codex"}
