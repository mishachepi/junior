"""Core abstractions for the review-runbook framework.

Two independent extension points (see docs-site/src/content/docs/architecture/runbooks.md):

- `Runbook` — one per *domain* (code review, Jira review, …). Owns its Context
  and Result schemas plus the domain logic: collect → render → publish.
- `Harness` — one per *LLM driver* (claudecode, codex, …). Schema-agnostic:
  it takes the output schema as a parameter, so a single set of engines serves
  every runbook.

Both are ABCs on purpose — this is a forkable framework, and a forgotten method
should fail loudly at instantiation, not silently under a type checker.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar, Generic, NamedTuple, TypeVar

from pydantic import BaseModel, Field, SerializeAsAny

if TYPE_CHECKING:
    from junior.config import Settings

C = TypeVar("C", bound=BaseModel)  # a runbook's context schema
R = TypeVar("R", bound=BaseModel)  # a runbook's result schema (raw LLM output)


class EnvVar(NamedTuple):
    """An environment variable a harness or runbook relies on.

    Harnesses/runbooks declare these so `junior config env` can list exactly
    what the chosen combination needs — without a central hardcoded table.
    """

    name: str           # env var name (use "A / B" when either satisfies it)
    required: bool      # True = needed; False = optional/auto-provided
    purpose: str        # one-line "what it's for"


class Usage(BaseModel):
    """Token accounting the engine measures and the runner threads through."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class LLMResult(BaseModel):
    """Envelope around a validated LLM output plus runtime metadata.

    `output` is an instance of whatever `output_schema` the caller requested.
    `SerializeAsAny` keeps the concrete subclass's fields on `model_dump()` —
    a bare `BaseModel` annotation would serialize them away.
    """

    output: SerializeAsAny[BaseModel]
    usage: Usage = Field(default_factory=Usage)
    errors: list[str] = Field(default_factory=list)


class Harness(ABC):
    """A driver for one way of calling an LLM. Shared across all runbooks."""

    #: short name, matches the HarnessKind member (e.g. "codex")
    name: ClassVar[str]
    #: True if the engine reads repository files itself (claudecode/codex);
    #: runbooks use this to decide whether to inline a full diff or not.
    file_access: ClassVar[bool] = False
    #: LLMSettings field names this harness actually honors (for `config show`).
    config_fields: ClassVar[tuple[str, ...]] = ()
    #: env vars this harness needs (for `config env`).
    env_vars: ClassVar[tuple[EnvVar, ...]] = ()
    #: one-line setup hint shown by `config env` (e.g. "authenticate the CLI").
    setup_note: ClassVar[str] = ""

    @abstractmethod
    def complete(
        self,
        *,
        system_prompt: str,
        user_message: str,
        output_schema: type[BaseModel],
        settings: "Settings",
    ) -> LLMResult:
        """Call the model and return an LLMResult whose `.output` is an
        instance of `output_schema`."""

    def is_ready(self) -> str | None:
        """Optional runtime self-check, run by `junior list` only when this
        harness is installed. Verifies the *environment* (CLI authenticated,
        provider key exported) — not the package, which `junior list` already
        checked. Return a short status, ideally ``"ready"`` or
        ``"not ready: <why>"``; ``None`` (default) = no check implemented, so
        the listing shows just the install status.

        Keep it cheap and import-free of the harness's heavy deps — it runs for
        every installed harness on a plain `junior list`.
        """
        return None


class Runbook(ABC, Generic[C, R]):
    """One review domain. A fork subclasses this and registers it by name."""

    name: ClassVar[str]
    #: one-line "what it reviews & where it posts" (for `junior list`).
    description: ClassVar[str] = ""
    #: whether the project dir must be a git repo (preflight checks for `.git`).
    #: False for runbooks that don't touch git (e.g. weather_advice).
    needs_git: ClassVar[bool] = False
    context_model: ClassVar[type[BaseModel]]
    result_model: ClassVar[type[BaseModel]]
    #: context/output field names this runbook uses (for `config show`).
    config_fields: ClassVar[tuple[str, ...]] = ()
    #: env vars this runbook needs to publish (for `config env`).
    env_vars: ClassVar[tuple[EnvVar, ...]] = ()

    # --- phase 1: collect ---
    @abstractmethod
    def collect(self, settings: "Settings") -> C:
        """Gather domain context. May dispatch internally (gitlab/github/local)."""

    # --- phase 2 inputs: what the LLM sees ---
    @abstractmethod
    def render(self, context: C, settings: "Settings", *, file_access: bool) -> str:
        """Turn context into the user message. `file_access` tells whether the
        chosen engine reads files itself (so a full diff need not be inlined)."""

    def system_prompt(self, settings: "Settings") -> str:
        """Role + rules. Override per domain; default is empty."""
        return ""

    # --- phase 3: publish ---
    @abstractmethod
    def publish(
        self,
        settings: "Settings",
        result: R,
        usage: Usage,
        *,
        errors: list[str],
    ) -> None:
        """Custom publish — run ONLY when `--publish` is set: post to a platform,
        render a pretty terminal view, write somewhere of your choosing.

        Without `--publish`, the framework emits `render_output()` to stdout/`-o`
        instead and never calls this (the raw output stays out of the publish
        sink). `errors` carries the harness's partial-failure notes
        (`LLMResult.errors`) so a runbook can surface them.
        """

    def render_output(self, result: R) -> str:
        """The default output (no `--publish`): the raw LLM result, unformatted
        and pipe-/file-safe so `-o FILE` (or a redirect) captures it cleanly.
        Default is pretty JSON; override to change the serialization."""
        return result.model_dump_json(indent=2)

    # --- validation ---
    def validate(self, settings: "Settings", *, publish_enabled: bool) -> list[str]:
        """Runbook-specific config checks (e.g. publish needs a token). Default: none."""
        return []

    # --- exit-code policy ---
    def is_blocking(self, result: R) -> bool:
        """Whether this result should make CI fail (exit 1). Default: never."""
        return False

    # --- optional hooks ---
    def is_empty(self, context: C) -> bool:
        """Whether there's nothing to review (skip the LLM). Default: never."""
        return False

    def summary(self, result: R) -> dict:
        """Key/value pairs for the final `done` log line. Default: none."""
        return {}

    def output_destination(self, settings: "Settings", *, publish_enabled: bool) -> str:
        """Human-readable sink for the final `done` log (`output=...`).

        Default: the platform (runbook name) when publishing, else the output
        file or stdout. Override when the runbook writes somewhere else (e.g. a
        terminal-only runbook that ignores `output.output_file`)."""
        if publish_enabled:
            return self.name
        return settings.output.output_file or "stdout"
