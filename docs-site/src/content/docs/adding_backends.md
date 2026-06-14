---
title: "Adding Runbooks and Harnesses"
---

# Adding Runbooks and Harnesses

Junior is a forkable framework with **two formal extension interfaces** (Runbook and Harness,
**Runbook × Harness**), both ABCs in `src/junior/runbook/base.py`, plus a small registry
that wires them together:

| Interface | What it is | One per | How it's selected |
|-----------|-----------|---------|-------------------|
| `Runbook[Ctx, Result]` | A full review *domain* — collect → render → harness → publish, platform included | domain (code review, Jira review, …) | `--runbook NAME` / `settings.runbook` |
| `Harness` | An *LLM driver* — schema-agnostic, takes the output schema as a parameter | LLM way of calling a model (claudecode, codex, …) | `--harness NAME` / `settings.llm.harness` |

> [!NOTE]
> These are ABCs **on purpose**. This is a forkable framework: a forgotten method
> should fail loudly at instantiation, not slip past a type checker.

The two interfaces are independent. A single set of harnesses serves *every* runbook, because
harnesses never know the output schema ahead of time — the runbook hands them one.

```
Runbook (domain)              Harness (driver)
-----------------              ----------------
collect(settings) -> Ctx       complete(*, system_prompt, user_message,
render(ctx, ...)  -> str   ─▶            output_schema, settings) -> LLMResult
publish(result, usage, ...)    file_access: ClassVar[bool]
```

There is **no separate platform/collector/publisher selector**. The platform is
part of each runbook. The modules under `junior.collect.*` and `junior.publish.*` are
just helper libraries that a runbook's `collect()` / `publish()` call directly.

---

## Adding a Harness

A harness is one way to call an LLM. Add one to support a new model provider, SDK, or
CLI. The whole job is **implementing one interface** (`Harness`, two methods — one of
them optional) plus two one-line registrations; the cross-harness contract tests pick
the new harness up automatically.

> [!TIP]
> A complete, real worked example is the `pi` harness
> (`src/junior/harnesses/pi.py`, ~200 lines): a subprocess CLI driver with no native
> structured-output mode, so it also shows the prompt-embedded-schema pattern and a
> tolerant JSON parser. It was written exactly by following the steps below.

### Step 1: Create the module

```
src/junior/harnesses/my_harness.py
```

Expose a module-level `HARNESS` instance implementing `Harness`:

```python
"""My custom LLM harness."""

import structlog
from pydantic import BaseModel

from junior.config import Settings
from junior.runbook.base import Harness, LLMResult, Usage

logger = structlog.get_logger()


class MyHarness(Harness):
    name = "my_harness"         # matches the HarnessKind member
    file_access = False         # True if the harness reads repo files itself
    config_fields = ("model",)  # LLMSettings fields you honor (for `config show`)
    env_vars = ()               # EnvVar tuples you need (for `config env`)
    setup_note = ""             # one-line setup hint shown by `config env`

    def is_ready(self) -> str | None:
        # Optional env/CLI self-check shown by `junior list` (e.g. "ready" /
        # "not ready: `mycli` not found"). Keep it cheap — no SDK imports.
        return None

    def complete(
        self,
        *,
        system_prompt: str,
        user_message: str,
        output_schema: type[BaseModel],
        settings: Settings,
    ) -> LLMResult:
        # Call the model however you like. Return an LLMResult whose `.output`
        # is a *validated instance of output_schema* (not the schema class).
        output = output_schema(...)  # parse/validate the model's response
        return LLMResult(
            output=output,
            usage=Usage(input_tokens=0, output_tokens=0, total_tokens=0),
            errors=[],  # partial-failure notes the runbook can surface
        )


HARNESS = MyHarness()  # the registry looks up this exact attribute name
```

Key points:

- `complete()` is **schema-agnostic**. `output_schema` is a parameter — return
  `LLMResult.output` as a validated instance of it. The same harness serves every
  runbook.
- Set `file_access = True` if the harness reads repository files itself (like
  `claudecode` / `codex`). Runbooks check this in `render()` to decide whether to
  inline a full diff (file-access harnesses don't need it).
- Populate `Usage` for token accounting; the runner threads it through to publish.
- Put partial-failure notes in `LLMResult.errors` — runbooks can surface them.
- **Lazy-import any heavy SDK inside `complete()`**, not at module top level — the
  registry imports every harness module for `junior list` / `config show`, and that
  must stay cheap (see `pydantic.py` / `deepagents.py`).
- If the engine has no native structured-output mode, embed the schema in the system
  prompt and validate the reply yourself — `pi.py` shows the pattern
  (`_OUTPUT_CONTRACT` + `_parse_response`).

### Step 2: Add the enum member

The `HarnessKind` enum value is the harness's module path; the registry resolves it via
`importlib.import_module(...).HARNESS`:

```python
# config.py
class HarnessKind(_ModulePathEnum):
    PYDANTIC = "junior.harnesses.pydantic"
    CODEX = "junior.harnesses.codex"
    CLAUDECODE = "junior.harnesses.claudecode"
    DEEPAGENTS = "junior.harnesses.deepagents"
    PI = "junior.harnesses.pi"
    MY_HARNESS = "junior.harnesses.my_harness"   # <-- add
```

### Step 3: Register for `junior list`

Add one `HARNESS_META` entry in `runbook/registry.py` — a description, the pip extra
name, and a "probe" package checked with `find_spec` (so listing never imports a heavy
SDK). A pure-subprocess harness has nothing to probe:

```python
HARNESS_META[HarnessKind.MY_HARNESS] = ("one-line description", "my_harness", "some_sdk")
# subprocess-only (no Python extra):     ("one-line description", "", "")
```

### Step 4: Update validation (if needed)

If your harness manages its own auth (like the CLI-driven `codex` / `claudecode` / `pi`),
add it to the skip list in `Settings._validate_review()` so it isn't forced to provide
an API key:

```python
if harness in (HarnessKind.CODEX, HarnessKind.CLAUDECODE, HarnessKind.PI,
               HarnessKind.MY_HARNESS):
    return []
```

### Step 5: Add a dependency extra (if needed)

```toml
# pyproject.toml
[project.optional-dependencies]
my_harness = ["some-sdk>=1.0"]
```

Done. `--harness my_harness` (or `HARNESS=my_harness`) now drives any runbook — and the
cross-harness contract tests (`tests/test_harnesses.py`) cover the new member
automatically because they parametrize over `HarnessKind`. Add a deep test file
(mocked subprocess / SDK) per the existing `tests/test_pi_harness.py` pattern.

---

## Adding a Runbook

A runbook is a full review domain: it owns its **Context** and **Result** schemas and
the domain logic (collect → render → harness → publish). To add one, subclass
`Runbook[CtxModel, ResultModel]`.

> [!TIP]
> For a complete, working **non-code-review** example, read `src/junior/runbooks/weather/` (`weather_advice`): it collects live weather instead of a git diff and asks the harness what to wear — no git, no platform, no API key. Having no platform, it repurposes `--publish` as a presentation toggle (`--publish` → pretty Rich panel; default → plain text). Run it with `junior run --runbook weather_advice`. It's the smallest end-to-end runbook in the repo and a good copy-paste starting point.

```python
from junior.config import Settings
from junior.runbook.base import Runbook, Usage
from junior.runbook.registry import register_runbook


@register_runbook
class JiraReview(Runbook[JiraContext, JiraFindings]):
    name = "jira_review"
    context_model = JiraContext
    result_model = JiraFindings

    def collect(self, settings: Settings) -> JiraContext:
        from junior_jira.api import fetch_issue   # keep heavy imports lazy
        ...

    def render(self, context: JiraContext, settings: Settings, *, file_access: bool) -> str:
        # Build the user message. `file_access` tells you whether the chosen harness
        # reads files itself, so you can skip inlining bulky content.
        ...

    def system_prompt(self, settings: Settings) -> str:
        return "You are a Jira reviewer. …"   # optional; default is empty

    def publish(
        self,
        settings: Settings,
        result: JiraFindings,
        usage: Usage,
        *,
        errors: list[str],
    ) -> None:
        ...   # runs ONLY with --publish: post / pretty-render / write somewhere
```

**Output model.** Without `--publish`, the framework emits `render_output(result)`
(default: the raw result as JSON) to `-o FILE` or stdout — you don't write output
yourself. `publish()` runs **only** with `--publish` and is where the custom
side-effect lives (post to a platform, print a Rich panel, run a script).

Required: `name`, `context_model`, `result_model`, and `collect()`, `render()`,
`publish()`. Optional overrides: `system_prompt()`, `render_output()` (the
no-`--publish` output; default JSON), `validate()`, `is_blocking()`, `is_empty()`,
`summary()`, `needs_git` (default `False`), `output_destination()` (the sink shown
in the final `done` log).

The runner calls them in order: `collect` → `render` → the harness's `complete()` (with
`result_model` as the output schema) → `publish`.

### Four ways to ship a runbook

#### 1. Built-in (in this repo)

Put it under `src/junior/runbooks/<pkg>/` and make that package's `__init__.py` import
the module(s) that define the `@register_runbook` classes:

```python
# src/junior/runbooks/jira_review/__init__.py
from junior.runbooks.jira_review import runbook  # noqa: F401  (registers)
```

The registry scans every subpackage of `junior.runbooks` and imports it, which runs the
registration. Nothing else to wire.

> [!TIP]
> Keep heavy collect/publish imports **lazy** (inside the methods, as the built-in
> code-review runbooks do). Importing the package must stay cheap — a missing optional
> dependency should not crash discovery, only disable that one runbook.

#### 2. External pip plugin (no fork)

A third-party package declares an entry point in its own `pyproject.toml`:

```toml
[project.entry-points."junior.runbooks"]
jira_review = "junior_jira.runbook:JiraReview"
```

Then:

```bash
pip install junior-jira
junior run --runbook jira_review
```

The registry loads everything in the `junior.runbooks` entry-point group automatically.

#### 3. Direct path (quick experiments)

Point `--runbook` (or `runbook:` in config) at a `module:ClassName` spec — no packaging
or registration needed:

```bash
junior run --runbook "my_pkg.runbook:JiraReview"
```

#### 4. Repo-local (in `.junior/runbooks/`)

Keep the runbook's code **inside the repository you review**, under
`<project>/.junior/runbooks/`. Two layouts, both auto-loaded:

```
.junior/runbooks/weather/weather.py   # folder per runbook (preferred — split across files)
.junior/runbooks/quick.py             # single-file runbook
```

Each must expose a `@register_runbook` class (exactly like a built-in). The runbooks root
is added to `sys.path`, so a folder runbook can split its `collect` / `render` / `publish`
across sibling modules and lazy-import them.

This is **opt-in** — it executes code shipped in the repo, so it's off by default:

```yaml
# .junior.yaml
local_runbooks: true
runbook: weather
```

```bash
junior run            # loads .junior/runbooks/, runs `weather`
junior config list    # opt-in local runbooks appear here too
```

> [!WARNING]
> `local_runbooks: true` runs Python from the repository. Only enable it in repos you
> trust — the same trust model as a `Makefile` or a git hook. See
> [prompt_injection.md](prompt_injection.md).

> [!TIP]
> Set `needs_git = False` on a runbook that doesn't diff a git repo (the default for the
> base `Runbook`; `CodeReviewRunbook` sets it `True`). Then it runs in any directory,
> no `.git` required. Override `output_destination()` so the final `done` log names your
> real sink (e.g. `"terminal"`).

##### Manifest runbooks (no Python — any language)

A repo-local runbook can also be a **YAML manifest** instead of a Python class — the
phases are then ordinary commands (sh, Python, anything). Drop a `<name>.yaml` (or
`manifest.yaml`) in the runbook folder:

```yaml
# .junior/runbooks/joke/joke.yaml
name: joke
description: tell a joke about a topic
schema: schema.json        # JSON-Schema for the AI result; omit → {"result": "<string>"}
system_prompt: prompt.md   # path or inline text
collect: sh ./collect.sh   # STDOUT becomes the user message; omit → read Junior's STDIN
publish: sh ./publish.sh   # receives the AI's validated JSON on STDIN
needs_git: false
```

```
.junior/runbooks/joke/
  joke.yaml      # the manifest
  schema.json    # { "type":"object", "properties": { "setup": {...}, "punchline": {...} } }
  prompt.md      # the system prompt / instructions
  collect.sh     # prints the user message (e.g. the topic)
  publish.sh     # does something with the result JSON (print, POST, write a file…)
```

Junior turns `schema.json` into the harness's output schema, runs `collect` → harness →
`publish`, and exposes `JUNIOR_PROJECT_DIR` + `JUNIOR_CONTEXT_<KEY>` (from `--context
KEY=VAL`) to your scripts. Same opt-in (`local_runbooks: true`) and trust model.

> A manifest needs at least a `system_prompt` or a `collect`; everything else has a
> default — no `schema` → `{"result": "<string>"}`, no `collect` → the user message is
> read from Junior's stdin (that's how `junior run | junior run` chains work), no
> `publish` → the result JSON is printed. The machinery lives in
> `src/junior/runbooks/script/`.

**The full manifest reference, the minimal one-file runbook, and the pipeline-chaining
recipe live on [Runbooks in YAML](script_runbooks.md).** A complete, copy-paste manifest
runbook (weather → what to wear, scripts in `python3`, no API key) is in
[`examples/runbooks/weather/`](examples/runbooks/weather/) — drop it into
`.junior/runbooks/weather/`, set `local_runbooks: true`, and run
`junior run --runbook weather-advice`.

---

## The Built-in Code-Review Family

Junior ships the code-review domain as a family of runbooks that share the base class
`CodeReviewRunbook` (`src/junior/runbooks/code_review/base.py`). They all review a git
diff with the same context schema (`CollectedContext`), render, prompt, and result schema
(`LLMReviewOutput`) — only *where the diff comes from* (collect) and *where the review
goes* (publish) differ:

| Runbook name | Source | Publishes to |
|---------------|--------|--------------|
| `local_review` | local git diff | stdout / `-o` file — no platform |
| `github_pr_review` | GitHub PR | PR review comments |
| `gitlab_pr_review` | GitLab MR | MR note + discussion threads |
| `bitbucket_pr_review` | Bitbucket DC PR | PR comment + inline comments |

The base class holds the shared `render()`, `system_prompt()`, `is_blocking()`,
`is_empty()`, `summary()`, and the `publish()` template method; each subclass implements
just `collect()` and `_post_to_platform()`. To add another platform to this family,
subclass `CodeReviewRunbook`, set `name`, and fill in those two hooks (plus
`_publish_requirements()` for `validate`).

---

## Removing a Runbook or Harness

**Runbook (built-in):** delete its package under `src/junior/runbooks/`, or remove the
import from the parent package's `__init__.py`. The registry simply stops discovering it.
External plugins are removed by uninstalling the package.

**Harness:** delete `src/junior/harnesses/<name>.py`, remove its `HarnessKind` member, drop
it from any validation skip list in `config.py`, and remove its `pyproject.toml` extra.

Dispatch is fully decoupled — no other files reference harnesses or runbooks by hand.

---

## Shared Helper Libraries

The code-review runbooks lean on these helper modules (call them, don't reimplement):

| Module | Helpers |
|--------|---------|
| `junior.collect.core` | `collect_base()`, `enrich_with_metadata()` |
| `junior.runbooks.code_review.render` | `build_user_message()` |
| `junior.runbooks.code_review.instructions` | `build_review_prompt()`, `BASE_RULES`, project-instruction reading |
| `junior.publish.core` | `format_summary()`, `format_inline_comment()`, `MAX_INLINE_COMMENTS` |

## Checklists

**New harness**

- [ ] `src/junior/harnesses/<name>.py` with a module-level `HARNESS` instance
- [ ] `complete()` returns `LLMResult` whose `.output` is a validated `output_schema`
- [ ] `file_access` set correctly (`True` if it reads repo files itself)
- [ ] `HarnessKind` member added in `config.py`
- [ ] Validation skip list updated (if it manages its own auth)
- [ ] `pyproject.toml` extra added (if it has deps)
- [ ] Tested: `junior run --harness <name>`

**New runbook**

- [ ] `Runbook[Ctx, Result]` subclass with `name`, `context_model`, `result_model`
- [ ] `collect()`, `render()`, `publish()` implemented (heavy imports kept lazy)
- [ ] Registered one of four ways: `@register_runbook` (built-in), `junior.runbooks` entry point (plugin), `--runbook module:ClassName` (direct path), or repo-local `.junior/runbooks/` (opt-in `local_runbooks`)
- [ ] Tested: `junior run --runbook <name>`
