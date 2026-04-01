"""Configuration from environment variables and .env files."""

from enum import Enum
from pathlib import Path
from typing import Self

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class _ModulePathEnum(str, Enum):
    """Base enum where value is a Python module path.

    Supports short names via env vars: AGENT_BACKEND=pydantic resolves to
    AgentBackend.PYDANTIC ("junior.agent.pydantic").
    """

    @classmethod
    def _missing_(cls, value: object) -> "Enum | None":
        if not isinstance(value, str):
            return None
        for member in cls:
            if member.name.lower() == value.lower():
                return member
        return None


class CollectorBackend(_ModulePathEnum):
    GITHUB = "junior.collect.github"
    GITLAB = "junior.collect.gitlab"
    LOCAL = "junior.collect.local"


class AgentBackend(_ModulePathEnum):
    PYDANTIC = "junior.agent.pydantic"
    CODEX = "junior.agent.codex"
    CLAUDECODE = "junior.agent.claudecode"
    DEEPAGENTS = "junior.agent.deepagents"


class PublishBackend(_ModulePathEnum):
    GITHUB = "junior.publish.github"
    GITLAB = "junior.publish.gitlab"
    LOCAL = "junior.publish.local"


# --- Module-level constants ---

_DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-5.4-mini",
    "anthropic": "claude-opus-4-6",
}

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # Platform tokens — presence determines platform (gitlab/github)
    gitlab_token: str = ""
    github_token: str = ""

    # AI keys
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # GitLab CI auto-populated variables
    ci_project_id: int | None = None
    ci_merge_request_iid: int | None = None
    ci_merge_request_title: str = ""
    ci_merge_request_description: str = ""
    ci_merge_request_source_branch_name: str = ""
    ci_merge_request_target_branch_name: str = "main"
    ci_merge_request_diff_base_sha: str | None = None
    ci_commit_sha: str | None = None
    ci_server_url: str = "https://gitlab.com"
    ci_project_dir: str = "."

    # GitHub Actions variables
    github_repository: str = ""  # "owner/repo"
    github_event_number: int | None = None  # PR number

    # Backend selection
    agent_backend: AgentBackend = AgentBackend.PYDANTIC

    # Review tuning
    model_name: str = ""
    model_provider: str = ""
    prompts: str = "security,logic,design"
    prompts_dir: str = ""
    source: str = "auto"  # auto, staged, commit, branch
    max_file_size: int = 100_000
    max_concurrent_agents: int = 3
    log_level: str = "INFO"

    # Publish options
    publish_output: str = ""

    # Extra context from CLI
    context: dict[str, str] = {}        # --context KEY="text" → prompt instructions
    context_files: dict[str, str] = {}  # --context-file KEY=path → data files

    # --- Field validators ---

    @field_validator("ci_project_dir", mode="before")
    @classmethod
    def resolve_project_dir(cls, v: str) -> str:
        return str(Path(v).resolve())

    @field_validator("model_provider", mode="before")
    @classmethod
    def normalize_model_provider(cls, v: str) -> str:
        v = v.strip().lower()
        if v and v not in ("openai", "anthropic"):
            raise ValueError(f"MODEL_PROVIDER must be 'openai' or 'anthropic', got '{v}'")
        return v

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in ("DEBUG", "INFO", "WARNING", "ERROR"):
            raise ValueError(f"LOG_LEVEL must be DEBUG|INFO|WARNING|ERROR, got '{v}'")
        return v

    # --- Model validator ---

    @model_validator(mode="after")
    def check_platform_tokens(self) -> Self:
        if self.gitlab_token and self.github_token:
            raise ValueError("Both GITLAB_TOKEN and GITHUB_TOKEN are set — remove one.")
        return self

    # --- Computed properties ---

    @property
    def resolved_provider(self) -> str:
        """Auto-detect provider from API key if not set."""
        if self.model_provider:
            return self.model_provider
        if self.openai_api_key:
            return "openai"
        if self.anthropic_api_key:
            return "anthropic"
        return ""

    @property
    def resolved_model(self) -> str:
        """Return model name, with sensible default per provider."""
        if self.model_name:
            return self.model_name
        return _DEFAULT_MODELS.get(self.resolved_provider, "")

    @property
    def model_string(self) -> str:
        """Build provider:model string for AI backends.

        Assumes resolved_provider and resolved_model are valid.
        Call preflight() first to catch configuration errors.
        """
        return f"{self.resolved_provider}:{self.resolved_model}"

    @property
    def resolved_collector(self) -> CollectorBackend:
        """Auto-detect collector from token presence."""
        if self.gitlab_token:
            return CollectorBackend.GITLAB
        if self.github_token:
            return CollectorBackend.GITHUB
        return CollectorBackend.LOCAL

    @property
    def resolved_publisher(self) -> PublishBackend:
        """Auto-detect publisher from token presence."""
        if self.gitlab_token:
            return PublishBackend.GITLAB
        if self.github_token:
            return PublishBackend.GITHUB
        return PublishBackend.LOCAL

    # --- Runtime validation (called from CLI before pipeline starts) ---

    def preflight(self, *, review: bool = True, publish: bool = False) -> list[str]:
        """Collect all configuration errors before starting the pipeline."""
        errors: list[str] = []
        errors.extend(self._validate_context_files())
        if review:
            errors.extend(self._validate_review())
        if publish:
            errors.extend(self._validate_publish())
        return errors

    def _validate_context_files(self) -> list[str]:
        errors = []
        for key, path in self.context_files.items():
            if not Path(path).is_file():
                errors.append(f"--context-file '{key}': file not found: {path}")
        return errors

    def _validate_review(self) -> list[str]:
        if self.agent_backend in (AgentBackend.CODEX, AgentBackend.CLAUDECODE):
            return []  # these backends manage their own auth

        errors = []
        provider = self.resolved_provider
        model = self.resolved_model

        if not provider:
            errors.append(
                "MODEL_PROVIDER is required. Set MODEL_PROVIDER=openai or MODEL_PROVIDER=anthropic "
                "(env var, .env, or --config file). Or set OPENAI_API_KEY / ANTHROPIC_API_KEY for auto-detection."
            )
        if provider and not model:
            errors.append(
                f"MODEL_NAME is required for provider '{provider}' "
                "(or use a provider with a known default model)."
            )
        return errors

    def _validate_publish(self) -> list[str]:
        publisher = self.resolved_publisher
        if publisher == PublishBackend.LOCAL:
            return ["--publish requires GITLAB_TOKEN or GITHUB_TOKEN."]

        errors = []
        if publisher == PublishBackend.GITLAB:
            if not self.ci_project_id:
                errors.append("CI_PROJECT_ID is required (are you running in GitLab CI?)")
            if not self.ci_merge_request_iid:
                errors.append("CI_MERGE_REQUEST_IID is required (is this an MR pipeline?)")
        elif publisher == PublishBackend.GITHUB:
            if not self.github_repository:
                errors.append("GITHUB_REPOSITORY is required")
            if not self.github_event_number:
                errors.append("GITHUB_EVENT_NUMBER (PR number) is required")
        return errors
