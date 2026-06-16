---
title: "Adding a Runbook"
---

# Adding a Runbook

A **runbook** is a full review *domain*: it owns its **Context** and **Result** schemas
and the domain logic — collect → render → harness → publish, platform included. It's one
of Junior's two extension interfaces; the other is the [Harness](adding_harnesses.md).
Both are ABCs in `src/junior/runbook/base.py`.

```
Runbook (domain)
----------------
collect(settings) -> Ctx
render(ctx, settings, *, file_access) -> str
publish(result, usage, *, errors)
```

> [!NOTE]
> `Runbook` is an ABC **on purpose**. This is a forkable framework: a forgotten method
> should fail loudly at instantiation, not slip past a type checker.

The two interfaces are independent — a single set of harnesses serves *every* runbook,
because harnesses never know the output schema ahead of time; the runbook hands them one.
There is **no separate platform/collector/publisher selector**: the platform is part of
each runbook. The modules under `junior.collect.*` and `junior.publish.*` are just helper
libraries that a runbook's `collect()` / `publish()` call directly.

To add a runbook, subclass `Runbook[CtxModel, ResultModel]`.

> [!TIP]
> For a complete, working **non-code-review** example, read `src/junior/runbooks/weather/` (`weather_advice`): it collects live weather instead of a git diff and asks the harness what to wear — no git, no platform, no API key. Having no platform, it repurposes `--publish` as a presentation toggle (`--publish` → pretty Rich panel; default → the raw result as JSON). Run it with `junior run --runbook weather_advice`. It's the smallest end-to-end runbook in the repo and a good copy-paste starting point.

```python
from junior.config import Settings
from junior.runbook.base import Runbook, Usage
from junior.runbook.registry import register_runbook


@register_runbook
class JiraReview(Runbook[JiraContext, JiraFindings]):
    name = "jira_review"
    context_model = JiraContext
    result_model = JiraFindings
    SYSTEM_PROMPT = "You are a Jira reviewer."   # one-line role; the base appends user --prompts

    def collect(self, settings: Settings) -> JiraContext:
        from junior_jira.api import fetch_issue   # keep heavy imports lazy
        ...

    def render(self, context: JiraContext, settings: Settings, *, file_access: bool) -> str:
        # Build the user message. `file_access` tells you whether the chosen harness
        # reads files itself, so you can skip inlining bulky content.
        ...

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
`publish()`. Set a one-line `SYSTEM_PROMPT` for the model's role — the base
`system_prompt()` assembles it plus any user `--prompt`s, so you rarely override the
method (the code-review runbooks do, to append their rules). Optional overrides:
`render_output()` (the no-`--publish` output; default JSON), `validate()`,
`is_blocking()`, `is_empty()`, `summary()`, `needs_git` (default `False`),
`output_destination()` (the sink shown in the final `done` log).

The runner calls them in order: `collect` → `render` → the harness's `complete()` (with
`result_model` as the output schema) → `publish`.

## Four ways to ship a runbook

### 1. Built-in (in this repo)

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

### 2. External pip plugin (no fork)

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

### 3. Direct path (quick experiments)

Point `--runbook` (or `runbook:` in config) at a `module:ClassName` spec — no packaging
or registration needed:

```bash
junior run --runbook "my_pkg.runbook:JiraReview"
```

### 4. Repo-local (in `.junior/runbooks/`)

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

#### Manifest runbooks (no Python — any language)

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

## Shared Helper Libraries

The code-review runbooks lean on these helper modules (call them, don't reimplement):

| Module | Helpers |
|--------|---------|
| `junior.collect.core` | `collect_base()`, `enrich_with_metadata()` |
| `junior.runbooks.code_review.render` | `build_user_message()` |
| `junior.runbooks.code_review.instructions` | `build_review_prompt()`, `BASE_RULES` |
| `junior.publish.core` | `format_summary()`, `format_inline_comment()`, `MAX_INLINE_COMMENTS` |

## Removing a runbook

Delete its package under `src/junior/runbooks/`, or remove the import from the parent
package's `__init__.py` — the registry simply stops discovering it. External plugins are
removed by uninstalling the package. Dispatch is fully decoupled — no other files
reference runbooks by hand.

## Checklist

- [ ] `Runbook[Ctx, Result]` subclass with `name`, `context_model`, `result_model`
- [ ] `collect()`, `render()`, `publish()` implemented (heavy imports kept lazy)
- [ ] Registered one of four ways: `@register_runbook` (built-in), `junior.runbooks` entry point (plugin), `--runbook module:ClassName` (direct path), or repo-local `.junior/runbooks/` (opt-in `local_runbooks`)
- [ ] Tested: `junior run --runbook <name>`
