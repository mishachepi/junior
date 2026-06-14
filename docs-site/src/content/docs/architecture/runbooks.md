---
title: "Runbooks — generic review framework (design)"
---

# Runbooks — the generic review framework

Junior is a small *review-runbook framework*. A **runbook** owns one domain
(collect → render → publish against its own schemas); a set of shared, schema-
agnostic **LLM harnesses** drive the model for every runbook. The built-in
runbooks review code diffs, but nothing in the framework is git-shaped.

This page is the deep-dive on those two abstractions. For the high-level picture
see [Architecture](../architecture.md); to add your own, see
[Adding runbooks & harnesses](../adding_backends.md).

## Why a framework

The data flowing between phases is git/MR-shaped — `CollectedContext` in,
`LLMReviewOutput` out:

```python
project_id, mr_iid, mr_title, source_branch, target_branch, labels,
full_diff, changed_files, comments, ...
```

That's the schema of *one domain* ("review a code diff"). The moment a fork wants
a runbook that reviews something else — a Jira ticket, a design doc, a release
checklist — those fields are dead weight and the wrong shape. So the data shape
flowing between phases is **not** global: each runbook brings its own. The
stable part — collect → process → publish, driven by a shared LLM caller — is
what the framework keeps fixed.

## Runbook × Harness

Junior has exactly two independent extension points. Keeping them independent is
the whole design. There is no third "platform" selector — platform (GitLab / GitHub /
local) is folded into a runbook's own `collect`/`publish`.

```
  RUNBOOK (domain)                    LLM HARNESS (shared)
  one class per domain                 one HARNESS per LLM driver
  ┌───────────────────────────┐        ┌───────────────────────────┐
  │ local_review              │        │ claudecode                │
  │ github_pr_review          │  uses  │ codex                     │
  │ gitlab_pr_review          │ ─────► │ pydantic                  │
  │ …a fork's runbook        │        │ deepagents                │
  └───────────────────────────┘        └───────────────────────────┘
  brings its own Context + Result      schema-agnostic: takes the
  schemas, collect/render/publish      output_schema as a parameter
```

- A **`Runbook`** is the unit a fork implements. It owns its `Context` and
  `Result` schemas and the domain logic (collect, render-for-LLM, publish). The
  platform variants (GitLab/GitHub/local) are runbooks in the same family, not a
  separate selector.
- A **`Harness`** is shared across all runbooks. It knows nothing about code,
  Jira, or diffs — it takes a system prompt, a user message, and a target
  **output schema**, calls the model, and returns a validated object of that
  schema plus token usage.

The key move: **the output schema is a parameter of the harness, not a hard-coded
type.** That's what lets one set of harnesses serve every domain. The code-review
runbooks ask the harness for `LLMReviewOutput`; a fork's `JiraReview` asks the
same harness for `TicketAssessment`.

## Interfaces (ABC, not Protocol)

Both abstractions live in `src/junior/runbook/base.py` as abstract base classes,
deliberately, because this is a **forkable framework**:

- **Runtime enforcement.** Forget a method → `TypeError: Can't instantiate
  abstract class …` immediately. `Protocol` only checks under a type checker,
  which a forker may never run, surfacing mistakes as obscure `AttributeError`s
  later.
- **An obvious extension anchor.** `class JiraReview(Runbook[...])` says exactly
  what to subclass and what to implement.
- **A home for shared defaults.** `system_prompt()`, `validate()`,
  `is_blocking()`, `is_empty()`, and `summary()` all have base implementations a
  fork overrides only as needed.

### The LLM harness

```python
from abc import ABC, abstractmethod
from typing import ClassVar
from pydantic import BaseModel, Field, SerializeAsAny


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class LLMResult(BaseModel):
    """The validated model output + runtime metadata the harness adds."""
    output: SerializeAsAny[BaseModel]      # an instance of the requested output_schema
    usage: Usage = Field(default_factory=Usage)
    errors: list[str] = Field(default_factory=list)   # partial-failure notes


class Harness(ABC):
    """A driver for one way of calling an LLM. Shared by all runbooks."""

    name: ClassVar[str]                    # matches the HarnessKind member
    file_access: ClassVar[bool] = False    # True if the harness reads repo files itself

    @abstractmethod
    def complete(
        self,
        *,
        system_prompt: str,
        user_message: str,
        output_schema: type[BaseModel],    # ← from runbook.result_model
        settings: "Settings",
    ) -> LLMResult:
        """Call the model and return an LLMResult whose .output is an
        instance of output_schema."""
```

The five harnesses (`junior.harnesses.{claudecode,codex,pydantic,deepagents,pi}`) each
implement `complete` and expose a module-level `HARNESS` instance. The schema is
passed in, never hard-coded, and each harness wires it through its own mechanism:

| Harness | `file_access` | How `output_schema` is applied |
|--------|---------------|--------------------------------|
| `claudecode` | `True` | `claude -p … --json-schema <schema>` |
| `codex` | `True` | strict JSON schema via openai's `to_strict_json_schema` |
| `pydantic` | `False` | a single structured call with `output_type=output_schema` |
| `deepagents` | `False` | a submit tool whose `args_schema=output_schema` |
| `pi` | `True` | schema embedded in the system prompt, reply validated with `model_validate` |

> [!NOTE]
> `pydantic` and `deepagents` make a **single structured call** for the requested
> schema — not the old per-prompt sub-agent fan-out. `file_access` lets a runbook
> skip inlining a full diff for harnesses that read files themselves.

Harnesses are resolved by the `HarnessKind` enum, whose value is the harness module
path; `registry.get_harness` imports it and reads `HARNESS`:

```python
class HarnessKind(_ModulePathEnum):
    PYDANTIC   = "junior.harnesses.pydantic"
    CODEX      = "junior.harnesses.codex"
    CLAUDECODE = "junior.harnesses.claudecode"
    DEEPAGENTS = "junior.harnesses.deepagents"
    PI         = "junior.harnesses.pi"
```

### The runbook

```python
from abc import ABC, abstractmethod
from typing import ClassVar, Generic, TypeVar
from pydantic import BaseModel

C = TypeVar("C", bound=BaseModel)    # this domain's context schema
R = TypeVar("R", bound=BaseModel)    # this domain's result schema (raw LLM output)


class Runbook(ABC, Generic[C, R]):
    """One review domain. A fork subclasses this and registers it by name."""

    name: ClassVar[str]
    context_model: ClassVar[type[BaseModel]]   # C — for JSON round-trip (--from-file)
    result_model: ClassVar[type[BaseModel]]    # R — the schema handed to the harness
    needs_git: ClassVar[bool] = False          # preflight requires a .git repo?

    # --- phase 1: collect ---
    @abstractmethod
    def collect(self, settings: "Settings") -> C:
        """Gather domain context. May dispatch internally (gitlab/github/local)."""

    # --- phase 2 inputs ---
    @abstractmethod
    def render(self, context: C, settings: "Settings", *, file_access: bool) -> str:
        """Turn context into the user message. file_access tells whether the harness
        reads files itself (so a full diff need not be inlined)."""

    def system_prompt(self, settings: "Settings") -> str:
        """Role + rules. Override per domain; default is empty."""
        return ""

    # --- phase 3: publish (only with --publish) ---
    @abstractmethod
    def publish(
        self, settings: "Settings", result: R, usage: Usage,
        *, errors: list[str],
    ) -> None:
        """Custom publish — runs ONLY with --publish (post / pretty render / script)."""

    def render_output(self, result: R) -> str:                    # no --publish output
        return result.model_dump_json(indent=2)                   # default: raw JSON

    # --- validation + policy hooks ---
    def validate(self, settings, *, publish_enabled) -> list[str]: return []
    def is_blocking(self, result: R) -> bool: return False   # exit 1 on CI?
    def is_empty(self, context: C) -> bool: return False      # skip the LLM?
    def summary(self, result: R) -> dict: return {}           # final "done" line
    def output_destination(self, settings, *, publish_enabled) -> str: ...  # done-log sink
```

### The runner (generic)

`run_runbook` (`src/junior/runbook/runner.py`) ties one runbook to one harness.
It is domain-agnostic and never mentions diffs or MRs. Collection is the
**caller's** concern — the runner takes an already-collected context — so
`junior run --from-file ctx.json` can bypass `collect()`:

```python
def run_runbook(runbook, harness, context, settings, *, publish_enabled) -> LLMResult:
    result = harness.complete(
        system_prompt=merge_system_prompt(           # runbook default + user layer
            runbook.system_prompt(settings),
            list(settings.llm.system_prompt),
        ),
        user_message=runbook.render(context, settings, file_access=harness.file_access),
        output_schema=runbook.result_model,         # ← R schema
        settings=settings,
    )
    if publish_enabled:                              # custom publish only with --publish;
        runbook.publish(                            # otherwise the CLI writes render_output()
            settings, result.output, result.usage, errors=result.errors,
        )
    return result
```

`junior dry-run -o ctx.json` serializes `context` (tagged with the runbook name
so `--from-file` knows which runbook produced it). The exit code is
`1 if runbook.is_blocking(result.output) else 0`.

## LLM settings

Harness selection, model, keys, prompts, and limits live in one group,
`settings.llm` (`LLMSettings`) — renamed from the old `settings.review`. It
mirrors a split between the **system prompt** (role/identity) and the **task**:

```python
class LLMSettings(BaseSettings):
    harness: HarnessKind = HarnessKind.CLAUDECODE      # which LLM driver
    model: str = ""                                    # "provider:model" or ""
    system_prompt: list[str] = []                      # inline | file://  (role layer)
    # API keys, max_file_size, max_tokens_per_agent …
```

> [!NOTE]
> `llm.harness` (env `HARNESS`, flag `--harness`) is canonical. The old
> `llm.backend` / `BACKEND` / `--backend` is kept as a deprecated alias.

`system_prompt` is an **extra** layer the user can add on top of the runbook's
own `system_prompt()` default — the runner merges them. The task layer for code
review is the runbook's own `context.prompts`. Both accept inline text or
`file://...` URIs via the shared `prompt_loader`.

## The built-in code-review family

The built-in code-review runbooks all review a git diff with the same `CollectedContext`
in and `LLMReviewOutput` out, so they share a base class `CodeReviewRunbook`
(`src/junior/runbooks/code_review/base.py`). It holds everything common —
`render`, `system_prompt`, `result_model`, `is_blocking`, `is_empty`, `summary`,
and a **template-method `publish`** that (only with `--publish`) assembles a
`ReviewResult` and delegates to `_post_to_platform`. Without `--publish`, all
of them emit the raw `LLMReviewOutput` as JSON via `render_output`. The variants
differ only in `collect` and `_post_to_platform`:

| Runbook | `collect` | `_post_to_platform` (`--publish`) | `validate` requires |
|----------|-----------|-----------------------------------|---------------------|
| `local_review` | local git diff | renders pretty Markdown locally | — |
| `github_pr_review` | GitHub PR via API | PR review comments | `GITHUB_TOKEN`, repo, PR number |
| `gitlab_pr_review` | GitLab MR via API | MR note + inline threads | `GITLAB_TOKEN`, `CI_PROJECT_ID`, MR iid |
| `bitbucket_pr_review` | Bitbucket DC PR via API | PR comment + inline comments | `BITBUCKET_URL` / `TOKEN` / `PROJECT` / `REPO` / `PR_ID` |

Where the shared pieces come from:

| Framework slot | Implementation |
|---|---|
| `context_model` | `CollectedContext` (`junior.runbooks.code_review.models`) |
| `result_model` | `LLMReviewOutput` (`junior.runbooks.code_review.models`) |
| `render()` | `build_user_message()` (`code_review/render.py`) |
| `system_prompt()` | `build_review_prompt()` + `BASE_RULES` + AGENT.md (`code_review/instructions.py`) |
| `collect()` | `junior.collect.{local,github,gitlab}.collect(settings)` |
| `publish()` (`--publish`) | `_post_to_platform`: local → `junior.publish.local` Markdown; github/gitlab → `post_review(...)` |
| `render_output()` (no `--publish`) | the raw `LLMReviewOutput` as JSON (default hook) |
| `is_blocking()` | any critical comment **or** `recommendation == request_changes` |

Each variant imports the collect/publish helper it needs directly — there is no
central `resolved_collector` / `resolved_publisher` dispatch. `pre_formatted` (the
`--publish-file` shortcut) is handled by `publish_prepared`. Runtime fields
(`tokens_used`, `input/output_tokens`, `review_errors`) come from the shared
`LLMResult`/`Usage` envelope, assembled into a `ReviewResult` at publish time.

## Adding a runbook (Jira example)

```python
class JiraTicket(BaseModel):                 # any shape — no git fields
    key: str
    summary: str
    description: str
    acceptance_criteria: list[str]
    comments: list[str]

class TicketAssessment(BaseModel):           # the schema the LLM must return
    verdict: Literal["ready", "needs_work"]
    gaps: list[str]
    questions: list[str]

@register_runbook
class JiraReview(Runbook[JiraTicket, TicketAssessment]):
    name = "jira_review"
    context_model = JiraTicket
    result_model = TicketAssessment

    def collect(self, settings):  ...                 # hit Jira API → JiraTicket
    def render(self, ticket, settings, *, file_access):  ...   # ticket → text
    def publish(self, settings, result, usage, *, errors):  ...   # only with --publish
    def system_prompt(self, settings):
        return "You are a backlog-refinement reviewer. ..."
```

`JiraReview` gets all five LLM harnesses, the whole prompt/config mechanism, JSON
round-trip, and the CLI for free. It writes **zero** subprocess/LLM-calling code.

## Selecting & registering a runbook

Runbook selection is **explicit** — there is no token auto-detection and no
implicit default. Pick one with `--runbook NAME`, config `runbook:`, or env
`RUNBOOK`. Harnesses stay on `--harness`:

```bash
junior run --runbook local_review                  # review the local diff
junior run --runbook gitlab_pr_review --publish    # review an MR, post results
junior run --runbook jira_review --harness codex   # a fork's runbook
```

The registry (`src/junior/runbook/registry.py`) merges runbooks from four
sources:

1. **Built-in** — every subpackage of `junior.runbooks` is auto-discovered via a
   `pkgutil` scan (no hardcoded list); importing it runs its `@register_runbook`.
2. **External plugin** — a pip-installed package declaring a `junior.runbooks`
   entry point:

   ```toml
   [project.entry-points."junior.runbooks"]
   jira_review = "junior_jira.runbook:JiraReview"
   ```

3. **Direct path** — `--runbook "pkg.module:ClassName"` loads a `Runbook`
   subclass directly, an escape hatch for quick experiments.
4. **Repo-local** (opt-in `local_runbooks: true`) — `load_local_runbooks()` loads
   `<project>/.junior/runbooks/*.py` (`@register_runbook` classes) and YAML
   manifests driving a `ScriptRunbook` (any language). Executes repo code, so
   it's off by default. See [Adding runbooks](../adding_backends.md#4-repo-local-in-juniorrunbooks).

## Module layout

```
src/junior/
  runbook/                 ← the framework (domain-agnostic)
    base.py                 ← Runbook + Harness ABCs, LLMResult, Usage
    runner.py               ← run_runbook()
    registry.py             ← get_runbook (built-in + entry-point + path), get_harness
  harnesses/                ← shared LLM drivers (each exposes HARNESS)
    claudecode.py  codex.py  pydantic.py  deepagents.py  pi.py
  runbooks/
    code_review/            ← the built-in runbook family
      base.py               ← CodeReviewRunbook (shared render/prompt/publish)
      local.py  github.py  gitlab.py   ← per-platform collect + _post_to_platform
      models.py             ← CollectedContext, LLMReviewOutput, ReviewResult, …
      render.py             ← build_user_message()
      instructions.py       ← build_review_prompt() + BASE_RULES
    weather/                ← example non-code-review runbook (live weather → outfit)
    script/                 ← ScriptRunbook: YAML manifest (prompt + optional schema/collect/publish)
  collect/  publish/        ← platform helpers imported by the runbooks
```

## Settings, validation, exit codes

- Settings split into `settings.context` (the task/inputs), `settings.llm` (harness
  + role prompt + keys + limits), `settings.output` (output file, platform tokens,
  `publish` flag), plus top-level `settings.runbook` and `settings.log_level`.
- Validation is split: **generic** checks (context files, LLM API key) live in
  `Settings.preflight`; **runbook-specific** checks (publishing needs a token)
  live in `Runbook.validate`.
- Exit code comes from `Runbook.is_blocking` — for code review, a critical
  comment or a `request_changes` recommendation fails CI (exit 1).
