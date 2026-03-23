"""Tests for Settings validation — pydantic validators and runtime checks."""

import pytest
from pydantic import ValidationError

from junior.config import AgentBackend, CollectorBackend, PublishBackend, Settings


# ---------------------------------------------------------------------------
# Model-level validators (run at Settings construction)
# ---------------------------------------------------------------------------


class TestPlatformTokenValidation:
    """Both GITLAB_TOKEN and GITHUB_TOKEN set → must fail."""

    def test_both_tokens_raises(self):
        with pytest.raises(ValidationError, match="Both GITLAB_TOKEN and GITHUB_TOKEN"):
            Settings(gitlab_token="glpat-xxx", github_token="ghp_xxx")

    def test_only_gitlab_token_ok(self):
        s = Settings(gitlab_token="glpat-xxx", github_token="")
        assert s.resolved_collector == CollectorBackend.GITLAB
        assert s.resolved_publisher == PublishBackend.GITLAB

    def test_only_github_token_ok(self):
        s = Settings(gitlab_token="", github_token="ghp_xxx")
        assert s.resolved_collector == CollectorBackend.GITHUB
        assert s.resolved_publisher == PublishBackend.GITHUB

    def test_no_tokens_local(self):
        s = Settings(gitlab_token="", github_token="")
        assert s.resolved_collector == CollectorBackend.LOCAL
        assert s.resolved_publisher == PublishBackend.LOCAL


class TestModelProviderValidation:
    """MODEL_PROVIDER field_validator — normalize + validate choices."""

    def test_valid_openai(self):
        s = Settings(model_provider="openai")
        assert s.model_provider == "openai"

    def test_valid_anthropic(self):
        s = Settings(model_provider="anthropic")
        assert s.model_provider == "anthropic"

    def test_uppercase_normalized(self):
        s = Settings(model_provider="OpenAI")
        assert s.model_provider == "openai"

    def test_whitespace_stripped(self):
        s = Settings(model_provider="  anthropic  ")
        assert s.model_provider == "anthropic"

    def test_empty_allowed(self):
        s = Settings(model_provider="")
        assert s.model_provider == ""

    def test_invalid_raises(self):
        with pytest.raises(ValidationError, match="must be 'openai' or 'anthropic'"):
            Settings(model_provider="deepmind")


class TestLogLevelValidation:
    """LOG_LEVEL field_validator — normalize + validate choices."""

    def test_valid_levels(self):
        for level in ("DEBUG", "INFO", "WARNING", "ERROR"):
            s = Settings(log_level=level)
            assert s.log_level == level

    def test_lowercase_normalized(self):
        s = Settings(log_level="debug")
        assert s.log_level == "DEBUG"

    def test_invalid_raises(self):
        with pytest.raises(ValidationError, match="LOG_LEVEL must be"):
            Settings(log_level="VERBOSE")


# ---------------------------------------------------------------------------
# Auto-detection properties
# ---------------------------------------------------------------------------


class TestResolvedProvider:
    """resolved_provider and model_string."""

    def test_explicit_provider(self):
        s = Settings(model_provider="anthropic", openai_api_key="sk-xxx")
        assert s.resolved_provider == "anthropic"

    def test_fallback_openai_key(self):
        s = Settings(openai_api_key="sk-xxx")
        assert s.resolved_provider == "openai"

    def test_fallback_anthropic_key(self):
        s = Settings(anthropic_api_key="sk-ant-xxx")
        assert s.resolved_provider == "anthropic"

    def test_no_provider_no_key(self):
        s = Settings()
        assert s.resolved_provider == ""

    def test_model_string_openai(self):
        s = Settings(model_provider="openai", model_name="gpt-4o")
        assert s.model_string == "openai:gpt-4o"

    def test_model_string_default_model(self):
        s = Settings(model_provider="openai")
        assert s.model_string.startswith("openai:")

    def test_model_string_empty_without_provider(self):
        s = Settings()
        assert s.model_string == ":"


# ---------------------------------------------------------------------------
# Runtime validation via settings.preflight()
# ---------------------------------------------------------------------------


class TestValidateReview:
    """validate(review=True) — requires MODEL_PROVIDER for non-codex."""

    def test_no_provider_fails(self):
        s = Settings(agent_backend=AgentBackend.PYDANTIC)
        errors = s.preflight(review=True)
        assert any("MODEL_PROVIDER is required" in e for e in errors)

    def test_provider_set_ok(self):
        s = Settings(model_provider="openai", openai_api_key="sk-xxx")
        errors = s.preflight(review=True)
        assert errors == []

    def test_codex_skips_provider_check(self):
        s = Settings(agent_backend=AgentBackend.CODEX)
        errors = s.preflight(review=True)
        assert errors == []

    def test_no_review_skips_check(self):
        s = Settings()  # no model_provider
        errors = s.preflight(review=False)
        assert errors == []


class TestValidatePublish:
    """validate(publish=True) — checks platform-specific fields."""

    def test_no_token_fails(self):
        s = Settings()
        errors = s.preflight(publish=True)
        assert any("--publish requires" in e for e in errors)

    def test_gitlab_missing_project_id(self):
        s = Settings(gitlab_token="glpat-xxx")
        errors = s.preflight(review=False, publish=True)
        assert any("CI_PROJECT_ID" in e for e in errors)

    def test_gitlab_missing_mr_iid(self):
        s = Settings(gitlab_token="glpat-xxx", ci_project_id=123)
        errors = s.preflight(review=False, publish=True)
        assert any("CI_MERGE_REQUEST_IID" in e for e in errors)

    def test_gitlab_valid(self):
        s = Settings(
            gitlab_token="glpat-xxx",
            ci_project_id=123,
            ci_merge_request_iid=42,
            model_provider="openai",
        )
        errors = s.preflight(review=True, publish=True)
        assert errors == []

    def test_github_missing_fields(self):
        s = Settings(github_token="ghp_xxx")
        errors = s.preflight(review=False, publish=True)
        assert any("GITHUB_REPOSITORY" in e for e in errors)
        assert any("GITHUB_EVENT_NUMBER" in e for e in errors)

    def test_github_valid(self):
        s = Settings(
            github_token="ghp_xxx",
            github_repository="owner/repo",
            github_event_number=1,
            model_provider="openai",
        )
        errors = s.preflight(review=True, publish=True)
        assert errors == []


class TestValidateContextFiles:
    """preflight() checks --context-file paths."""

    def test_context_file_not_found(self):
        s = Settings(context_files={"lint_results": "/nonexistent/file.json"})
        errors = s.preflight(review=False)
        assert any("file not found" in e for e in errors)

    def test_empty_context_files_ok(self):
        s = Settings(context_files={})
        errors = s.preflight(review=False)
        assert errors == []

    def test_any_key_accepted(self, tmp_path):
        f = tmp_path / "rules.txt"
        f.write_text("be strict")
        s = Settings(context_files={"custom_rules": str(f)})
        errors = s.preflight(review=False)
        assert errors == []


class TestValidateCombined:
    """preflight() collects errors from all checks at once."""

    def test_multiple_errors_collected(self):
        s = Settings(
            context_files={"x": "/nonexistent"},
            model_provider="",
        )
        errors = s.preflight(review=True, publish=True)
        assert len(errors) >= 2
