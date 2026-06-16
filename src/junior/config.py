"""Configuration — three groups (Context, LLM, Output) + composite Settings.

Each group is a BaseSettings that reads its own env vars. The composite Settings
just plugs them together and provides preflight().

Config priority (highest wins): CLI flags → env vars → --config FILE → project
`.junior.{yaml,yml}` → ~/.config/junior/settings.{yaml,yml}.

Config files are **YAML only** (`--config -` reads YAML from stdin too). The same
config shape is used for project-level files, the global file, and ad-hoc
"presets" — copy `docs-site/src/content/docs/examples/configs/security.yaml` somewhere and pass
`--config FILE`. (Data dumps like `junior dry-run -o ctx.json` and run records
stay JSON — those are machine artifacts, not configs.)

Most keys nest under their group (`context:` / `llm:` / `output:`), but the
run-shaping knobs you set most often — `harness`, `model`, `publish`,
`output_file` (plus `runbook` / `log_level`) — are also accepted at the config
root as shorthand (`harness: codex` == `llm: {harness: codex}`).
"""

from __future__ import annotations

import os
import sys
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import structlog
import yaml
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# --- Config file paths ---

GLOBAL_CONFIG_DIR = Path.home() / ".config" / "junior"

# Auto-discovery — first match wins (.yaml preferred over .yml).
GLOBAL_CONFIG_CANDIDATES: tuple[Path, ...] = (
    GLOBAL_CONFIG_DIR / "settings.yaml",
    GLOBAL_CONFIG_DIR / "settings.yml",
)
LOCAL_CONFIG_CANDIDATES: tuple[str, ...] = (".junior.yaml", ".junior.yml")

# The wizard always writes YAML — one canonical config format everywhere.
GLOBAL_CONFIG_PATH = GLOBAL_CONFIG_DIR / "settings.yaml"


# --- Enums ---


class _CaseInsensitiveStrEnum(StrEnum):
    """StrEnum that resolves string lookups regardless of letter case."""

    @classmethod
    def _missing_(cls, value: object) -> StrEnum | None:
        if not isinstance(value, str):
            return None
        folded = value.lower()
        for member in cls:
            if member.value.lower() == folded:
                return member
        return None


class _ModulePathEnum(StrEnum):
    """Base enum where value is a Python module path; member name = short name.

    Lookup matches the short member name (e.g. "pydantic"), not the dotted
    module path — that's why this can't share `_missing_` with
    `_CaseInsensitiveStrEnum`.
    """

    @classmethod
    def _missing_(cls, value: object) -> StrEnum | None:
        if not isinstance(value, str):
            return None
        for member in cls:
            if member.name.lower() == value.lower():
                return member
        return None


class HarnessKind(_ModulePathEnum):
    PYDANTIC = "junior.harnesses.pydantic"
    CODEX = "junior.harnesses.codex"
    CLAUDECODE = "junior.harnesses.claudecode"
    DEEPAGENTS = "junior.harnesses.deepagents"
    PI = "junior.harnesses.pi"


class SourceMode(_CaseInsensitiveStrEnum):
    AUTO = "auto"
    STAGED = "staged"
    COMMIT = "commit"
    BRANCH = "branch"


class LogLevel(_CaseInsensitiveStrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


# --- Module-level constants ---

_DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-5.4-mini",
    "anthropic": "claude-opus-4-6",
}

_SUPPORTED_PROVIDERS = ("openai", "anthropic")

# Permission modes the `claude` CLI accepts for `--permission-mode`.
_CLAUDECODE_PERMISSION_MODES = ("default", "acceptEdits", "plan", "bypassPermissions")

_BASE_CONFIG = SettingsConfigDict(
    case_sensitive=False,
    extra="ignore",
    frozen=True,
    populate_by_name=True,
)


# --- Group 1: Context (what to review) ---


class ContextSettings(BaseSettings):
    """What to review — diff source, prompts, extra context, MR metadata."""

    model_config = _BASE_CONFIG

    project_dir: Path = Field(
        default=Path("."),
        validation_alias=AliasChoices("project_dir", "CI_PROJECT_DIR"),
    )
    source: SourceMode = SourceMode.AUTO
    base_sha: str | None = None
    target_branch: str = Field(
        default="main",
        validation_alias=AliasChoices(
            "target_branch", "CI_MERGE_REQUEST_TARGET_BRANCH_NAME"
        ),
    )
    # Each entry is either inline prompt text, or a `file://...` URI pointing
    # at a `.md` file. Relative `file://` paths are resolved against the
    # config file's directory before reaching Settings — by the time the
    # collector/agent sees this, every URI is absolute.
    prompts: list[str] = Field(default_factory=list)
    context: dict[str, str] = Field(default_factory=dict)
    context_files: dict[str, str] = Field(default_factory=dict)
    # Free-form task input from the positional CLI argument (`junior run "…"`).
    # Handed to the runbook's collect step; each collector decides what to do
    # with it (code_review reviews the text instead of a git diff, a script
    # runbook uses it as the user message). Data, not config — set per run.
    input_text: str = ""

    # CI auto-vars that feed the LLM prompt
    mr_title: str = Field(
        default="",
        validation_alias=AliasChoices("mr_title", "CI_MERGE_REQUEST_TITLE"),
    )
    mr_description: str = Field(
        default="",
        validation_alias=AliasChoices(
            "mr_description", "CI_MERGE_REQUEST_DESCRIPTION"
        ),
    )
    source_branch: str = Field(
        default="",
        validation_alias=AliasChoices(
            "source_branch", "CI_MERGE_REQUEST_SOURCE_BRANCH_NAME"
        ),
    )

    @field_validator("project_dir", mode="before")
    @classmethod
    def resolve_project_dir(cls, v: str | Path) -> Path:
        return Path(v).resolve()


# --- Group 2: LLM (how to call the model) ---


class ClaudeCodeSettings(BaseSettings):
    """claudecode-only knobs, nested under `llm.claudecode`; ignored by other harnesses."""

    model_config = _BASE_CONFIG

    # Maps to `claude -p --permission-mode`. Default `bypassPermissions` so the
    # CLI's built-in tools run unattended (junior is usually containerized);
    # tighten it (e.g. `acceptEdits`/`plan`) for untrusted content outside a sandbox.
    permission_mode: str = "bypassPermissions"

    @field_validator("permission_mode", mode="before")
    @classmethod
    def validate_permission_mode(cls, v: Any) -> Any:
        """Mirror `harness_by_name`: a human error instead of a bare enum dump.

        Note `""` is rejected too (a config typo should fail as a config error,
        not slip through to `claude --permission-mode ""` failing at runtime).
        """
        if isinstance(v, str) and v not in _CLAUDECODE_PERMISSION_MODES:
            known = ", ".join(_CLAUDECODE_PERMISSION_MODES)
            raise ValueError(f"unknown permission_mode '{v}'. Known: {known}")
        return v


class LLMSettings(BaseSettings):
    """How to call the LLM — harness (driver), model, API keys, limits.

    Domain-agnostic: shared by every runbook. The system prompt is the runbook's
    own (its `SYSTEM_PROMPT` role + the user's `context.prompts`).
    """

    model_config = _BASE_CONFIG

    # The LLM driver. `harness`/`HARNESS` is canonical; `backend`/`BACKEND` is a
    # deprecated alias kept for one version so existing configs/CI keep working.
    harness: HarnessKind = Field(
        default=HarnessKind.CLAUDECODE,
        validation_alias=AliasChoices("harness", "backend"),
    )

    @field_validator("harness", mode="before")
    @classmethod
    def harness_by_name(cls, v: Any) -> Any:
        """A human error message: pydantic's default for a bad enum value lists
        the module paths (`junior.harnesses.…`), which mean nothing to a user."""
        if (
            isinstance(v, str)
            and v
            and v not in {m.value for m in HarnessKind}  # full module path is valid too
            and HarnessKind._missing_(v) is None
        ):
            known = ", ".join(m.name.lower() for m in HarnessKind)
            raise ValueError(f"unknown harness '{v}'. Known: {known}")
        return v

    # Accepts "provider:model" or just "model". Provider is inferred from
    # the prefix, falling back to whichever API key is set.
    model: str = ""
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    # pydantic harness: cap the response tokens per call (0 = no cap).
    max_tokens_per_agent: int = 0
    # collection + pydantic file tools: skip files larger than this (bytes).
    max_file_size: int = 100_000
    # CLI harnesses (claudecode/codex/pi): kill the subprocess after this many
    # seconds. Lower it to fail fast on a stuck/runaway agent.
    timeout: int = 600
    # claudecode-only knobs (nested under `llm.claudecode`); other harnesses ignore it.
    claudecode: ClaudeCodeSettings = Field(default_factory=ClaudeCodeSettings)

    @field_validator("claudecode", mode="before")
    @classmethod
    def _coerce_claudecode(cls, v: Any) -> Any:
        """Ignore a non-mapping leaking in from the env.

        The field name collides with the bare `CLAUDECODE` env var that the
        Claude Code runtime sets (`CLAUDECODE=1`); pydantic-settings' env source
        feeds that `1` into this model field and validation would fail. Real
        config always arrives as a mapping/model, so drop anything else back to
        defaults. (Configure via YAML `llm.claudecode`, not an env var.)
        """
        if isinstance(v, (dict, ClaudeCodeSettings)):
            return v
        return {}

    @field_validator("model", mode="before")
    @classmethod
    def validate_model_format(cls, v: Any) -> str:
        if not v:
            return ""
        v = str(v).strip()
        if ":" in v:
            provider = v.partition(":")[0].strip().lower()
            if provider not in _SUPPORTED_PROVIDERS:
                raise ValueError(
                    f"unknown provider '{provider}' in --model. "
                    f"Supported: {', '.join(_SUPPORTED_PROVIDERS)}"
                )
        return v

    @property
    def harness_name(self) -> str:
        """The harness's short name (e.g. "claudecode") — its registry/UI label."""
        return self.harness.name.lower()

    @property
    def resolved_provider(self) -> str:
        """Provider from --model prefix, or fallback to API-key presence."""
        if ":" in self.model:
            return self.model.partition(":")[0].lower()
        if self.openai_api_key:
            return "openai"
        if self.anthropic_api_key:
            return "anthropic"
        return ""

    @property
    def resolved_model(self) -> str:
        """Model name without provider prefix, or per-provider default."""
        if ":" in self.model:
            return self.model.partition(":")[2]
        if self.model:
            return self.model
        return _DEFAULT_MODELS.get(self.resolved_provider, "")

    @property
    def model_string(self) -> str:
        """Build `provider:model` for SDK calls. Empty parts allowed; preflight catches them."""
        return f"{self.resolved_provider}:{self.resolved_model}"

    @property
    def display_model(self) -> str:
        """Model name safe to surface in logs/UI for the active harness.

        - pydantic/deepagents: SDK actually receives resolved_model.
        - claudecode: only show when model is explicitly set (the CLI defaults otherwise).
        - pi: passes the raw `--model provider/id` through; show it when set.
        - codex: the CLI picks its own model — don't claim one.
        """
        if self.harness in (HarnessKind.PYDANTIC, HarnessKind.DEEPAGENTS):
            return self.resolved_model
        if self.harness == HarnessKind.CLAUDECODE:
            return self.resolved_model if self.model else ""
        if self.harness == HarnessKind.PI:
            return self.model  # raw, e.g. "ollama/qwen3" — not provider:model
        return ""


# --- Group 3: Output (where to send) ---


class OutputSettings(BaseSettings):
    """Where to send — local file path, publish toggle, platform tokens, CI vars."""

    model_config = _BASE_CONFIG

    output_file: str = ""
    # Whether the runbook should publish to its platform (post the review).
    # Each runbook decides what this means; local_review ignores it.
    publish: bool = False
    # Write a machine-readable record of every run to `.junior/output/{ts}.json`.
    # On by default (auditability); disable with --no-record / output.record: false.
    record: bool = True
    gitlab_token: str = ""
    github_token: str = ""
    ci_server_url: str = "https://gitlab.com"

    # GitLab CI auto-vars used by the publisher
    ci_project_id: int | None = None
    ci_merge_request_iid: int | None = None
    ci_merge_request_diff_base_sha: str | None = None
    ci_commit_before_sha: str | None = None
    ci_commit_sha: str | None = None

    # GitHub Actions auto-vars used by the publisher
    github_repository: str = ""
    github_event_number: int | None = None
    github_event_before: str | None = None

    # Bitbucket Data Center vars used by the collector/publisher. Nothing is
    # auto-provided — Bitbucket DC has no pipelines of its own, so the user
    # sets these in their CI (Jenkins/Bamboo/TeamCity).
    bitbucket_url: str = ""
    bitbucket_token: str = ""
    bitbucket_project: str = ""
    bitbucket_repo: str = ""
    bitbucket_pr_id: int | None = None


# --- Top-level Settings ---


class Settings(BaseSettings):
    """Top-level — composes three groups + log level. preflight() collects errors."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    context: ContextSettings = Field(default_factory=ContextSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    output: OutputSettings = Field(default_factory=OutputSettings)
    # Which runbook (module) to run — registry name or "module:ClassName".
    # No magic: chosen explicitly via --runbook / RUNBOOK / config; there is no
    # implicit default. Empty → `junior run`/`dry-run` exit 2 with a hint.
    runbook: str = ""
    log_level: LogLevel = LogLevel.INFO
    # Opt-in: load repo-local runbooks from <project>/.junior/runbooks/ (each a
    # folder or .py exposing a @register_runbook class). OFF by default because
    # it executes code shipped in the repository — see docs-site/src/content/docs/prompt_injection.md.
    local_runbooks: bool = False

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip().upper()
        return v

    def preflight(self, *, review: bool = True) -> list[str]:
        """Generic, runbook-agnostic validation (context files + LLM harness).

        Runbook-specific checks (e.g. publish targets) live in
        `Runbook.validate()` and are run by the CLI alongside this.
        """
        errors: list[str] = []
        errors.extend(self._validate_context_files())
        errors.extend(self._validate_output_file())
        if review:
            errors.extend(self._validate_review())
        return errors

    def _validate_output_file(self) -> list[str]:
        """Catch an unwritable -o target up front, before any (paid) LLM call.

        Note `Path("")` is `Path(".")` — a directory — so `-o ""` lands here too.
        """
        of = self.output.output_file
        if not of:
            return []
        p = Path(of)
        if p.is_dir():
            return [
                f"output file is a directory: '{of}'. "
                "Pass a file path, or '-o -' to force stdout."
            ]
        if not p.parent.is_dir():
            return [f"output file directory does not exist: {p.parent}"]
        return []

    def _validate_context_files(self) -> list[str]:
        return [
            f"--context-file '{k}': file not found: {p}"
            for k, p in self.context.context_files.items()
            if not Path(p).is_file()
        ]

    def _validate_review(self) -> list[str]:
        harness = self.llm.harness
        # CLI-driven harnesses manage their own auth/model.
        if harness in (HarnessKind.CODEX, HarnessKind.CLAUDECODE, HarnessKind.PI):
            return []

        errors: list[str] = []
        provider = self.llm.resolved_provider
        if not provider:
            errors.append(
                "MODEL provider is required. Pass --model 'openai:gpt-...' or "
                "'anthropic:claude-...', or set OPENAI_API_KEY / ANTHROPIC_API_KEY "
                "for auto-detection."
            )
            return errors

        key = (
            self.llm.openai_api_key
            if provider == "openai"
            else self.llm.anthropic_api_key
        )
        if not key:
            env_name = f"{provider.upper()}_API_KEY"
            errors.append(
                f"{env_name} is required for harness '{harness.name.lower()}' "
                f"with provider '{provider}'."
            )
        return errors


# --- Config file discovery & loading ---


def _first_existing(paths: list[Path]) -> Path | None:
    for p in paths:
        if p.is_file():
            return p
    return None


def find_global_config() -> Path | None:
    return _first_existing(list(GLOBAL_CONFIG_CANDIDATES))


def _git_root(start: Path) -> Path | None:
    """The closest ancestor (or `start` itself) containing `.git`, if any."""
    for d in (start, *start.parents):
        if (d / ".git").exists():
            return d
    return None


def find_local_config() -> Path | None:
    """Find the project config: CWD first, then walking up to the repo root.

    Running junior from a subdirectory of the project must see the same
    `.junior.yaml` as running from the root (the git convention). The walk
    stops at the first directory containing `.git`, so a config outside the
    repository is never picked up; outside a repo only the CWD is checked.
    """
    cwd = Path.cwd()
    root = _git_root(cwd)
    dirs = [cwd]
    if root is not None and root != cwd:
        for d in cwd.parents:
            dirs.append(d)
            if d == root:
                break
    for d in dirs:
        hit = _first_existing([d / n for n in LOCAL_CONFIG_CANDIDATES])
        if hit:
            return hit
    return None


def _parse_config_text(text: str) -> dict:
    """Parse YAML config content into a dict (YAML is a JSON superset)."""
    if not text.strip():
        return {}
    data = yaml.safe_load(text)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("config root must be a mapping")
    return data


# Curated top-level shorthands: the run-shaping knobs you set most often can
# live at the config root instead of nested in a group. `harness: codex` is
# accepted as sugar for `llm: {harness: codex}`. Both forms work; on a conflict
# the top-level value wins. (Everything else still nests under its group.)
_TOP_LEVEL_SHORTHANDS: dict[str, tuple[str, str]] = {
    "harness": ("llm", "harness"),
    "model": ("llm", "model"),
    "publish": ("output", "publish"),
    "output_file": ("output", "output_file"),
}


def _promote_shorthands(cfg: dict) -> dict:
    """Fold top-level shorthands down into their groups (load direction).

    Run per config source *before* merging, so layer precedence (deep-merge on
    the nested keys) and env-shadowing keep working unchanged. Top-level wins
    over an explicit nested value in the same source.
    """
    for key, (group, field) in _TOP_LEVEL_SHORTHANDS.items():
        if key not in cfg:
            continue
        value = cfg.pop(key)
        grp = cfg.setdefault(group, {})
        if isinstance(grp, dict):
            grp[field] = value
    return cfg


def _flatten_shorthands(cfg: dict) -> dict:
    """Lift shorthand group fields up to the config root (save direction).

    The inverse of `_promote_shorthands`: keeps the on-disk file in the flat
    canonical form and prevents a stale nested duplicate surviving a deep-merge
    when the wizard re-saves. Top-level wins; emptied groups are dropped.
    """
    for key, (group, field) in _TOP_LEVEL_SHORTHANDS.items():
        grp = cfg.get(group)
        if isinstance(grp, dict) and field in grp:
            cfg.setdefault(key, grp.pop(field))
            if not grp:
                cfg.pop(group, None)
    return cfg


def _resolve_prompt_uris(cfg: dict, base_dir: Path) -> dict:
    """Resolve relative `file://` URIs in `context.prompts` against `base_dir`.

    Plain inline strings (no `file://` prefix) and already-absolute URIs are
    left as-is. We resolve at load time so the merged config carries
    absolute URIs only — callers don't need to know which file a prompt
    came from.
    """
    ctx = cfg.get("context")
    if isinstance(ctx, dict) and isinstance(ctx.get("prompts"), list):
        ctx["prompts"] = [_resolve_one_prompt_entry(str(p), base_dir) for p in ctx["prompts"]]
    return cfg


def _resolve_one_prompt_entry(entry: str, base_dir: Path) -> str:
    if not entry.startswith("file://"):
        return entry
    parsed = urlparse(entry)
    path = unquote(parsed.path)
    if parsed.netloc and parsed.netloc not in ("", "localhost"):
        # Treat `file://relative/path` (no leading `/`) as a relative path.
        path = parsed.netloc + path
    p = Path(path)
    if not p.is_absolute():
        p = (base_dir / p).resolve()
    return f"file://{p}"


def load_config_file(path: Path) -> dict:
    """Load and parse a single YAML config file, resolving file:// URIs."""
    text = path.read_text(encoding="utf-8")
    try:
        data = _parse_config_text(text)
    except yaml.YAMLError as e:
        raise ValueError(f"failed to parse {path}: {e}") from e
    return _resolve_prompt_uris(_promote_shorthands(data), path.parent.resolve())


def load_config_stdin() -> dict:
    """Load YAML config from stdin. Relative file:// URIs resolve against CWD."""
    text = sys.stdin.read()
    try:
        data = _parse_config_text(text)
    except yaml.YAMLError as e:
        raise ValueError(f"failed to parse stdin config: {e}") from e
    return _resolve_prompt_uris(_promote_shorthands(data), Path.cwd())


def load_configs(*, override_path: str | None = None) -> dict:
    """Merge configs from all layers.

    Precedence (lowest → highest, last wins):
      1. global   ~/.config/junior/settings.{yaml,yml}
      2. project  .junior.{yaml,yml}
      3. --config FILE  (or `--config -` for stdin)

    Top-level keys already set as env vars are dropped — env wins over file.
    """
    logger = structlog.get_logger()
    merged: dict = {}

    def _safe_load(path: Path) -> dict:
        try:
            return load_config_file(path)
        except (ValueError, OSError) as e:
            logger.warning("failed to load config", path=str(path), error=str(e))
            return {}

    global_path = find_global_config()
    if global_path:
        merged = _deep_merge(merged, _safe_load(global_path))

    local_path = find_local_config()
    if local_path:
        merged = _deep_merge(merged, _safe_load(local_path))

    if override_path:
        if override_path == "-":
            merged = _deep_merge(merged, load_config_stdin())
        else:
            path = Path(override_path)
            if not path.is_file():
                raise ValueError(f"Config file not found: {override_path}")
            merged = _deep_merge(merged, load_config_file(path))

    _warn_unknown_config_keys(merged, logger)
    return _drop_env_shadowed(merged)


# The config-file groups and their settings models.
_CONFIG_GROUPS: tuple[tuple[str, type], ...] = (
    ("context", ContextSettings),
    ("llm", LLMSettings),
    ("output", OutputSettings),
)
# Valid top-level config keys: Settings fields + the shorthands. Other group
# fields must nest under their group; a flat one (e.g. `source:`) is silently
# dropped by pydantic's extra="ignore", so we warn so the mistake is visible.
# (Shorthands never reach here — they're promoted into their group on load.)
_GROUP_FIELDS: dict[str, str] = {
    name: group for group, model in _CONFIG_GROUPS for name in model.model_fields
}


def _warn_unknown_config_keys(cfg: dict, logger) -> None:
    """Warn on top-level config keys that pydantic would silently ignore."""
    known_top_level = set(Settings.model_fields) | set(_TOP_LEVEL_SHORTHANDS)
    for key in cfg:
        if key in known_top_level:
            continue
        group = _GROUP_FIELDS.get(key)
        hint = f"did you mean {group}.{key}?" if group else "not a known setting"
        logger.warning("ignoring unknown config key", key=key, hint=hint)


def _field_env_names(model: type, fname: str) -> set[str]:
    """Env-var names that pydantic-settings would read for this field."""
    names = {fname.upper()}
    alias = model.model_fields[fname].validation_alias
    if isinstance(alias, AliasChoices):
        names.update(c.upper() for c in alias.choices if isinstance(c, str))
    elif isinstance(alias, str):
        names.add(alias.upper())
    return names


def _drop_env_shadowed(cfg: dict) -> dict:
    """Drop config values that an env var should override, so env wins over file.

    Implements the documented precedence (env > config file). File values reach
    pydantic as init args, which would otherwise outrank env; removing the keys
    whose env var is set lets pydantic-settings read them from the environment.
    Works for nested group fields (e.g. `HARNESS` → `llm.harness`), not just
    top-level keys.
    """
    env_upper = {k.upper() for k in os.environ}
    groups = dict(_CONFIG_GROUPS)
    out: dict = {}
    for key, value in cfg.items():
        model = groups.get(key)
        if model is not None and isinstance(value, dict):
            kept = {
                fname: fval
                for fname, fval in value.items()
                # Only scalar file values are env-shadowed. A nested-model field
                # (dict value, e.g. `llm.claudecode`) can't be expressed by a flat
                # env var, so a name collision (e.g. `CLAUDECODE=1`) must not drop it.
                if not (
                    fname in model.model_fields
                    and not isinstance(fval, dict)
                    and _field_env_names(model, fname) & env_upper
                )
            }
            if kept:
                out[key] = kept
        elif key.upper() not in env_upper:
            out[key] = value
    return out


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Recursively merge overlay into base; overlay wins on leaf collisions."""
    out = dict(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _merge_into_yaml(path: Path, config: dict) -> Path:
    """Deep-merge `config` into the YAML file at `path` (created if absent).

    Existing groups/keys outside `config` are preserved; a corrupt existing file
    is overwritten cleanly. Always writes YAML — one canonical config format.
    """
    existing: dict = {}
    if path.is_file():
        try:
            existing = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(existing, dict):
                existing = {}
        except (yaml.YAMLError, OSError):
            existing = {}

    # Canonicalise both sides to the flat shorthand form before merging, so a
    # re-save doesn't leave a stale nested duplicate (e.g. old `llm: {harness}`
    # lingering beside a new top-level `harness`).
    merged = _deep_merge(
        _flatten_shorthands(existing), _flatten_shorthands(dict(config))
    )
    path.write_text(
        yaml.safe_dump(merged, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return path


def save_global_config(config: dict) -> Path:
    """Save to the global config (~/.config/junior/settings.yaml)."""
    GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return _merge_into_yaml(GLOBAL_CONFIG_PATH, config)


def save_local_config(config: dict) -> Path:
    """Save to the project config (./.junior.yaml in the current directory)."""
    return _merge_into_yaml(Path(LOCAL_CONFIG_CANDIDATES[0]), config)
