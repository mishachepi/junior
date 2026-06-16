# Changelog

## 0.2.3 — 2026-06-17

- **Refactor: code-review models composed over the framework envelope + renamed.**
  `ReviewResult` is now a thin subclass of the shared `LLMResult` — it composes the
  LLM `output` with `usage` (token counts) and `errors` instead of flatly duplicating
  `summary`/`recommendation`/`comments` and unpacking tokens into `tokens_used`/
  `input_tokens`/`output_tokens`/`review_errors`. The count/blocking logic
  (`critical_count`, `high_count`, `has_blocking_issues`) moved onto `ReviewOutput`,
  the owner of `comments` + `recommendation`. Two context/output schemas were renamed:
  `CollectedContext` → `ReviewContext`, `LLMReviewOutput` → `ReviewOutput`.
  - *Breaking for forks* importing the old names or reading the old flat
    `ReviewResult` fields. The deprecated `junior.models` shim keeps
    `CollectedContext` / `LLMReviewOutput` as aliases for one version; update to
    `junior.runbooks.code_review.models`. `assemble_review_result(output, *, usage,
    errors=...)` replaces the old `tokens_used=…, review_errors=…` signature.
  - The raw (no `--publish`) JSON is now the `ReviewOutput` (summary / recommendation
    / comments); `ReviewResult` (with nested `usage`) is the publish-time envelope.
- **Refactor: collector comment finalisation deduplicated.** The repeated
  `MAX_COMMENTS = 50` + drop-empty / sort-by-`created_at` / keep-newest block in the
  gitlab/github/bitbucket collectors moved to a single
  `junior.collect.core.finalize_comments` helper (mirroring `publish/core`'s
  `MAX_INLINE_COMMENTS`). No behaviour change.

- **`claudecode` permission mode is now configurable.** The previously hard-coded
  `--permission-mode bypassPermissions` is set from the new nested knob
  `llm.claudecode.permission_mode` (default unchanged: `bypassPermissions`). Allowed
  values mirror the `claude` CLI — `default`, `acceptEdits`, `plan`, `bypassPermissions`;
  an unknown value fails fast in config validation. YAML only (set under `llm.claudecode`,
  not an env var). Tighten it (e.g. `plan`) when running on untrusted content outside a
  sandbox. `junior config show` lists it under `llm.claudecode` for the claudecode harness.
- **Security: the code-review runbook no longer inlines `AGENT.md` / `AGENTS.md` /
  `CLAUDE.md` into the system prompt.** Previously these files from the reviewed
  branch's working tree were read verbatim into the prompt, letting a PR rewrite the
  reviewer's own instructions (prompt poisoning). The runbook now reads no
  project-instruction files at all; a harness that wants project memory reads it from
  its own working directory (`claudecode` → `CLAUDE.md`, `codex` → `AGENTS.md`), while
  the SDK harnesses (`pydantic`/`deepagents`) get none. Removed
  `read_project_instructions` / `MAX_INSTRUCTIONS_CHARS`; `build_review_prompt` no
  longer takes `project_dir`.
- **New runbook setting `context.max_diff_chars`** (default `200000`; `0` = no cap). A
  hard ceiling on the inlined diff size that applies to *every* harness. Previously
  `INLINE_DIFF_MAX_CHARS` only gated the inline-vs-file-tools threshold for file-access
  harnesses, while the SDK harnesses (`pydantic`/`deepagents`) inlined the full diff
  unbounded — a cost/DoS hazard on a huge MR. Oversized diffs are truncated with a
  marker; a negative value is rejected in config validation.
- **Security: GitLab & Bitbucket warn when the access token would travel in
  cleartext.** A non-HTTPS `ci_server_url` (GitLab) / `bitbucket_url` now logs a
  warning in both the collect and publish paths (it does not hard-fail — local/intranet
  HTTP keeps working). The scheme check is case-insensitive; the token is never logged.
- **Prompt-file frontmatter parsing hardened.** `parse_prompt_file` treats `---` as
  YAML frontmatter only when it's the leading delimiter of the file (parsed with
  `yaml.safe_load`), so a `.md` prompt whose body contains `---` (a horizontal rule or
  a YAML example) is no longer mis-parsed as metadata.
- **`codex` no longer leaks a temp file when output-schema construction fails** — both
  temp files are created inside the `try`, and `finally` unlinks whichever exist.
- **`weather_advice` shows a real `0%` precipitation reading** instead of hiding it via
  a truthiness check (`None` = no data is still hidden).
- **Internal: the GitHub collector/publisher import `httpx` lazily** (inside the request
  methods, matching the Bitbucket backend), keeping registry scans / `junior list`
  cheap on a core install.

## 0.2.2 — 2026-06-15

- **Breaking: `local_review --publish` now renders to stdout, not to `-o`.** With
  `--publish` the runbook owns its output channel — `local_review` writes the Markdown
  review to **stdout** (redirect with `> file` to save it); `-o` / `output_file` is
  ignored. `-o` stays the sink for the **raw result JSON** on runs *without* `--publish`.
  Migration: replace `local_review --publish -o review.md` with
  `local_review --publish > review.md`.
- **Docs: fixed the "generate locally, then `--publish-file`" recipes.** They fed a `-o`
  file (raw JSON) into `--publish-file`, which expects a rendered Markdown review; the
  recipes now use `--publish > review.md`. (`faq.md`, `cli.md`, `README.md`.)
- **Docs pass.** Consolidated the 7-page runbook-example walkthrough into two pages
  (*Anatomy of a run* + *Review output in detail*), harmonized the five harness deep-dive
  pages to one section template, and verified pages against the source (system-prompt
  merge order, `LLMReviewOutput` vs `ReviewResult`, formatter output, CLI flags).
- **`llm.timeout` config knob** for the CLI harnesses (`claudecode` / `codex` / `pi`):
  the subprocess timeout (default 600s) is now configurable, so you can fail fast on a
  stuck or runaway agent (e.g. `llm.timeout: 120`). The timeout error now reports the
  actual value instead of a hard-coded "10 minutes".
- **`claudecode` "no StructuredOutput" failure now explains itself.** When the CLI
  returns without the `StructuredOutput` tool call (rate limit, refusal, or out of
  turns), the error names the likely cause and quotes what claude said as text instead —
  visible at error level without `-v`. Running with `-v` also dumps the full raw
  response (`claude response parsed` debug log) for deeper troubleshooting.
- **`claudecode` parses both structured-output shapes.** When the CLI returns no
  `StructuredOutput` tool_use, the harness now falls back to the result message's
  top-level `structured_output` field — so reviews keep parsing across CLI
  output-format versions. The current shape is unaffected (the tool_use is tried first).
- **System prompt unified to one channel.** Every runbook now declares a single-line
  `SYSTEM_PROMPT` role; the base `Runbook.system_prompt()` assembles it plus the user's
  `context.prompts` (`--prompt` / `--prompt-file`) through one shared helper
  (`prompt_loader.merge_prompts`).
- **Breaking: removed the `llm.system_prompt` config field** (the separate "role layer"
  the runner merged on top). It duplicated `context.prompts`; use `--prompt` /
  `--prompt-file` / `context.prompts` instead. Configs that set `llm.system_prompt`
  should move those entries to `context.prompts`.

## 0.2.1 — 2026-06-15

Maintenance release — no breaking changes.

- **`deepagents` harness deprecated.** It's the least reliable harness (skips the
  submit tool, struggles past ~30KB, no retry). Selecting it now prints a startup
  deprecation warning and it's marked deprecated in `config list harnesses` and the
  docs. Prefer `pydantic`.
- **Docker `pydantic` target now actually installs the pydantic harness** — it was
  building with `--extra gitlab` only, so `pydantic_ai` was missing and
  `--harness pydantic` failed at runtime with `No module named 'pydantic_ai'`.
  Now `--extra gitlab --extra pydantic`.
- **Docker `full` target installs the `pi` CLI** (`@earendil-works/pi-coding-agent`)
  so the `pi` harness works in the image; it bundles pydantic + codex + pi + deepagents.
- **Fixed the `pi` install instructions** everywhere (harness error message + docs):
  the CLI ships as `@earendil-works/pi-coding-agent`, not `@mariozechner/pi` (which
  installs an unrelated `pi-pods` binary).
- **`.dockerignore`** excludes `docs-site/`, `.junior/`, `.github/` — smaller build context.
- **Rewrote the CI guide** (`ci.md`) as a "Junior as a code-review tool in CI" page:
  the manual-button-on-MR GitLab pattern, trigger variants, image build + push, and the
  `--platform linux/amd64` runner-architecture gotcha.
- **Refreshed dependencies** to the latest compatible versions (`uv lock --upgrade`).

## 0.2.0 — 2026-06-14

0.2.0 is a large, breaking release that turns Junior from a hard-wired
code-review tool into a **runbook framework**: two independent extension
points — **runbook** (a module doing collect → render → LLM → publish) and
**harness** (the LLM driver), each behind an ABC — on top of a Typer CLI, YAML-only configs,
user-supplied prompts, and a lean per-extra install. The notes below are grouped
by theme; all of it ships in 0.2.0.

### New integrations: Bitbucket Data Center + the pi harness

- **New runbook `bitbucket_pr_review`** — reviews a pull request on **Bitbucket
  Data Center** (self-hosted; tested against the 1.0 REST API of Bitbucket DC 9.4)
  and, with `--publish`, posts a summary comment plus inline comments anchored to
  the diff (anchor rejections degrade to a general `file:line` comment). The diff
  is taken locally via git, using the PR's `toRef.latestCommit` from the API as
  the base; PR title/description and existing comment threads are fetched into
  the review context. Configured entirely via env (CI-friendly — Bitbucket DC has
  no pipelines of its own): `BITBUCKET_URL` (HTTPS only), `BITBUCKET_TOKEN`
  (HTTP access token, sent as `Bearer`), `BITBUCKET_PROJECT`, `BITBUCKET_REPO`,
  `BITBUCKET_PR_ID`. New `junior[bitbucket]` extra (httpx). See
  [CI Setup](docs-site/src/content/docs/ci.md) → Bitbucket Data Center.
- **New harness: `pi`** — drives the [pi coding agent](https://github.com/badlogic/pi-mono)
  CLI (`--harness pi`; core install, no Python extra). Provider-agnostic with
  first-class **local models**: configure Ollama/LM Studio/vLLM in
  `~/.pi/agent/models.json` and pass `--model provider/id` (no API key
  needed). Pi has no native structured-output flag, so the harness embeds the
  JSON Schema in the system prompt and validates the reply; file tools are
  read-only (`read,grep,find,ls`), runs are hermetic (no sessions, extensions,
  skills, or context files). The harness how-to in `adding_backends.md` was
  rewritten around it (steps now cover `HARNESS_META`, `is_ready()`, tests);
  new deep-dive page `agent_backends/pi.md`.
### Review quality, CLI UX & fixes

- **Breaking: no implicit default runbook.** `junior run` / `junior dry-run`
  now require the runbook to be chosen explicitly — `--runbook`, env `RUNBOOK`,
  or config `runbook:` (which `junior init` writes). With none set, the run
  exits 2 with a hint instead of silently reviewing the local diff. Predictable
  behavior over magic: a run never does something you didn't pick.
- **Breaking: the positional argument is now free-form INPUT text.**
  `junior run "def f(uid): …"` hands the text to the runbook's collect step and
  the collector decides what to do with it: code_review reviews the text
  instead of a git diff (no git repo required), a collect-less script runbook
  uses it as the user message (taking precedence over stdin). The project
  directory moved to `--project-dir PATH` (still an `--env PROJECT_DIR=…`
  alias); `junior runs [PROJECT_DIR]` is unchanged.

- **New `--env KEY=VALUE` flag** on `junior run` / `junior dry-run` (repeatable) —
  supply any env var inline instead of exporting it first. Same precedence as
  exported env vars (explicit CLI flags still win); inherited by the harness
  subprocess and script-runbook `collect`/`publish` commands. Complements
  `junior config env`, which lists the vars a harness + runbook combination
  needs: `junior run --runbook gitlab_pr_review --publish --env GITLAB_TOKEN=…`.
- **Scalar configuration flags are now `--env` aliases** — `--model`, `--source`,
  `--base-sha`, `--target-branch`, `-o`, `--publish`/`--no-publish`,
  `--no-record`, and `--project-dir` export their env var for the run
  (`--model X` ≡ `--env MODEL=X`). One override channel: observable precedence
  is unchanged (flags → env → config files), and a flag's value now reaches the
  harness subprocess and script-runbook commands through the environment.
  The primary selectors `--runbook` / `--harness` are deliberately *not*
  exported — a nested `junior run` inside a script-runbook command must not
  inherit the parent's runbook.
- **Fixed: `junior init` / `junior run -i` without a terminal crashed with a
  raw asyncio traceback.** Both wizards now exit 2 with a one-line error
  («…needs a terminal (stdin is not a TTY)») — relevant for CI and piped runs.
- **Friendlier errors.** An unknown `--harness` now lists the harness names
  («unknown harness 'x'. Known: pydantic, codex, …») instead of pydantic's
  module-path enum; settings errors drop the «Value error, » prefix; positional
  INPUT alongside `--from-file`/`--publish-file` is rejected instead of silently
  dropped. The `pi` harness's `--model provider/id` now shows in the plan/logs.
- **New docs page: Getting Started** — a guided five-minute onboarding path
  (install → `init` → `dry-run` → first review → run records); the site hero
  button now points there instead of the CLI reference.
- **Code review: small diffs are now inlined for `claudecode`/`codex` too.**
  Previously `file_access` harnesses got only a changed-files list and read the
  final file state themselves — which made regressions visible only in removed
  lines (e.g. a safe call replaced by an unsafe one) look like pre-existing
  code and get skipped (observed in practice: both CLI harnesses missed a
  parameterized-query → string-concat regression that the inline-diff harness
  caught). Now the diff is always part of the user message while ≤ 50k chars
  (`INLINE_DIFF_MAX_CHARS` in `runbooks/code_review/base.py`); file tools
  remain for context beyond the diff, and oversized diffs fall back to the old
  behavior.
- **`-o -` forces stdout.** `junior run -o -` explicitly resets an
  `output_file` coming from config back to stdout — previously there was no
  CLI way to undo a config-file sink. (`dry-run -o` still requires a real
  path — its `-o` saves the context JSON.)
- **Fixed: `-o ""` / `-o <dir>` crashed with a raw traceback** (`IsADirectoryError`)
  *after* the LLM call had already run and been paid for. An unwritable
  output target (directory, missing parent dir) is now caught in preflight
  (exit 2) before any collection or review.
- **New `junior runs` command** — the read side of the run record:
  `junior runs` lists the latest 20 records (timestamp, runbook, harness,
  tokens, blocking, summary), `junior runs last` prints the newest record's
  raw JSON to stdout (pipe-safe: `junior runs last | jq .output`). Optional
  `PROJECT_DIR` argument; pre-0.2.0 records (old `pipeline` key) still render.
- **Project config is now found from subdirectories.** `.junior.{yaml,yml}`
  discovery walks up from the current directory to the repository root (the
  first directory containing `.git`) — same convention as git itself. The walk
  never crosses the repo boundary, and without a repo only the CWD is checked.
- **Sticky-default guard:** a `runbook:` set in the *global* config
  (`~/.config/junior/`) that changes the effective runbook now logs a startup
  WARNING pointing at the project config / `--runbook` — a leftover global
  experiment no longer silently redefines what `junior run` does in every repo.
- **`run -i` now asks which runbook to run** (it asked harness/model/source/
  output but silently kept the configured runbook); the confirmation summary
  shows it too.
- **Raw-output discoverability:** when the raw result JSON lands on an
  interactive terminal, a one-line `--publish` hint is printed to stderr
  (TTY only — pipes and CI see byte-identical output and no hint).
- **Fixed: `junior dry-run -o ctx.json` crashed with `AttributeError`** for
  non-code-review runbooks (e.g. `weather_advice`) — the context saver assumed
  `changed_files`. It is now runbook-agnostic and logs the context type.
- **Oversized project instructions are truncated.** `AGENT.md`/`AGENTS.md`/
  `CLAUDE.md` content beyond 30k chars (`MAX_INSTRUCTIONS_CHARS`) is cut with a
  warning instead of silently inflating every review prompt.
- **`junior dry-run` calls out an empty context** ("`junior run` would stop
  here without calling the LLM") instead of just showing an empty table.
- **Internal: code-review domain models moved** from `junior/models.py` to
  `junior/runbooks/code_review/models.py` — the framework core (`junior.runbook`,
  `junior.cli`) is now fully domain-agnostic. `junior.models` remains as a
  deprecated re-export shim for one version; update imports.

### Runbook framework: runbook × harness, platform folded in

Junior is now a **runbook framework**, not a hard-wired code-review tool. The old
"platform" (local/gitlab/github) is no longer a separate selector; it is part of
each runbook.

#### What changed

- **Unified publish vs raw output (all runbooks).** One rule everywhere: **no
  `--publish`** → the framework emits the runbook's `render_output(result)`
  (default: the raw result as pretty JSON) to `-o FILE` or stdout — clean and
  pipe-safe; **`--publish`** → the runbook's custom `publish()` runs instead
  (post to platform / pretty render / run a script) and the raw output is *not*
  printed (it's still in the run record). `Runbook.publish(settings, result,
  usage, *, errors)` lost its `publish_enabled` arg — it's called **only** when
  publishing. New `Runbook.render_output()` hook (default JSON) defines the
  no-publish output. Wiring: `runner.run_runbook` publishes only when enabled;
  `cli.actions.emit_output` writes the raw output otherwise.
  - `local_review` **no longer rejects `--publish`** — with `--publish` it
    renders the pretty Markdown locally; without it you get raw JSON.
    `weather_advice`: `--publish` → Rich panel, default → JSON. Script runbooks:
    the `publish` command runs only with `--publish`.
  - **`--publish` is now tri-state**: `--publish` / `--no-publish` override
    `output.publish` from config (e.g. `--no-publish` forces raw even when the
    config sets `publish: true`). Click flags don't accept `=value`, so use
    `--no-publish` rather than `--publish=false`.
  - `-o` / `output.output_file` now carries the **raw** output (when not
    publishing), not a pre-rendered review.
- **`--publish` is a per-runbook contract flag** (also `output.publish: true` in
  config): `local_review` renders Markdown locally, `github_pr_review` /
  `gitlab_pr_review` post to the PR/MR, `weather_advice` prints a Rich panel.
- **Two ABCs (`src/junior/runbook/base.py`):** `Runbook[Ctx, Result]` (owns its
  Context/Result schemas + collect/render/system_prompt/publish/validate) and
  `Harness` (schema-agnostic: `complete(*, system_prompt, user_message,
  output_schema, settings) -> LLMResult`). The output schema is a parameter, so
  one harness serves any runbook.
- **LLM driver = "harness".** `agent/` → `harnesses/`; ABC `LLMEngine` → `Harness`;
  enum `AgentBackend` → `HarnessKind`; each module exposes a `HARNESS` instance.
  Settings `llm.backend` → `llm.harness`; env `BACKEND` → `HARNESS`; flag
  `--backend` → `--harness` (old names kept as a **deprecated alias** for one
  version). `pydantic`/`deepagents` do a single structured call (no fan-out).
- **rich for user output, structlog for logs.** User-facing output goes through
  rich (`src/junior/cli/console.py`); status/errors go to stderr. structlog is
  logs-only (stderr). dry-run is a rich table.
- **Run records.** Every successful `junior run` writes a secret-free JSON trace
  to `<project_dir>/.junior/output/{timestamp}.json` (`src/junior/run_record.py`):
  runbook, harness, model, usage, errors, summary, blocking, structured output.
  On by default (`output.record`); disable with `--no-record` / `output.record: false`.
- **Runbooks as modules.** Built-in code-review family: `local_review` (default),
  `github_pr_review`, `gitlab_pr_review`, `bitbucket_pr_review` — sharing
  `CodeReviewRunbook`. Domain
  message builders moved `agent/core/` → `runbooks/code_review/{render,instructions}.py`.
- **Example runbook `weather_advice`** (`src/junior/runbooks/weather/`) — proves
  the framework generalizes past code review: collect = live weather via ip-api +
  open-meteo (stdlib urllib, key-free, no git), result = "what to wear", publish =
  a Rich terminal panel when `--publish` is set, else plain JSON. `junior run
  --runbook weather_advice`; `--context location="City"` / `lat=..,lon=..` to
  override geolocation. A small copy-paste template for custom runbooks.
- **`dry-run` is runbook-agnostic.** `preview_run` no longer assumes the
  code-review context shape: code-review contexts still get the changed-files
  table, any other runbook's context (e.g. `weather_advice`) is shown as a
  generic field dump. So `junior dry-run --runbook weather_advice` works with no
  git repo.
- **`Runbook.needs_git`** (ClassVar, default `False`; `CodeReviewRunbook` =
  `True`) gates the preflight `.git` check, so non-git runbooks run in any
  directory. **`Runbook.output_destination()`** lets a runbook declare the sink
  shown in the final `done` log.
- **Repo-local runbooks** (4th way to add a runbook). With `local_runbooks:
  true` (opt-in), Junior loads runbooks from `<project>/.junior/runbooks/` —
  folder-per-runbook (`weather/weather.py`) or single file (`quick.py`), each a
  `@register_runbook` class; the runbooks root goes on `sys.path` so a runbook
  can span sibling modules. OFF by default because it executes repo code
  (`registry.load_local_runbooks`). They appear in `junior config list` too.
- **Manifest runbooks (no Python).** A repo-local runbook can be a YAML manifest
  (`.junior/runbooks/<name>/<name>.yaml`) with `system_prompt`, `schema`
  (JSON-Schema for the AI result), and `collect`/`publish` **shell commands** —
  Junior builds the output schema from the JSON-Schema, feeds `collect`'s stdout
  to the harness, and pipes the validated JSON to `publish`'s stdin
  (`JUNIOR_PROJECT_DIR` + `JUNIOR_CONTEXT_<KEY>` exported to the scripts).
  Everything but one of `system_prompt`/`collect` is optional: without `schema`
  the result shape defaults to `{"result": "<string>"}` (runs still emit
  validated JSON), and without `collect` the user message is read from Junior's
  **stdin** — which makes shell pipelines of Juniors work out of the box:
  `junior run --runbook a | junior run --runbook b --publish`. Machinery in
  `src/junior/runbooks/script/` (`ScriptRunbook`, `runbook_from_manifest`,
  `json_schema_to_model`, `DEFAULT_SCHEMA`). Same `local_runbooks` opt-in.
  Docs page: `script_runbooks.md` ("Runbooks in YAML") with the manifest
  reference and the chaining recipe.
- **Runbook selection is explicit — no token auto-detection.** Choose with
  `--runbook NAME` / config `runbook:` / env `RUNBOOK` (default `local_review`).
  Four ways to add one: built-in subpackage (auto-discovered), external pip
  plugin (entry-point group `junior.runbooks`), `--runbook "pkg.module:ClassName"`,
  or a repo-local runbook under `.junior/runbooks/` (opt-in `local_runbooks`).
- **`--platform` removed.** `resolved_collector` / `resolved_publisher` /
  `Platform` enum / the both-tokens validation error are gone. Publish targets are
  decided by the runbook; publish requirements validated by `Runbook.validate()`.
- **`settings.review` → `settings.llm`** (class `ReviewSettings` → `LLMSettings`);
  config key `review:` → `llm:`. Added `llm.system_prompt` (role layer; task layer
  stays `context.prompts`), `output.publish`, and `output.record`.
- **`junior config show` = your current effective config + status** (replaces the
  idea of a separate `junior status`). It resolves the configured harness +
  runbook and prints *their* `context:`/`llm:`/`output:` fields at your **real
  current values** (no flags needed), with a comment header reporting the config
  source(s) and the harness's readiness. `--harness X` / `--runbook Y` scope to a
  different combination. The body stays valid YAML you can pipe into a config.
  Secrets/CI vars are never shown.
- **New `junior config env`.** Shows the env vars a harness + runbook rely on
  (API keys, platform tokens, CI vars), each marked required/optional and
  set/unset. Defaults to your config; override with `--harness` / `--runbook`.
- **Harnesses & runbooks self-describe their config.** New `EnvVar` plus
  `config_fields` / `env_vars` (and harness `setup_note`) ClassVars on the
  `Harness` / `Runbook` ABCs drive `config show` / `config env` — no central
  table, so plugins describe themselves.
- **Removed dead `llm` settings.** `temperature`, `max_tokens`, and
  `max_concurrent_agents` were never wired to anything (leftover from the old
  fan-out) — dropped from `LLMSettings` and the dry-run plan. The real tuning
  knobs are `max_tokens_per_agent` (pydantic) and `max_file_size`.
- **Top-level config shorthands.** `harness`, `model`, `publish`, `output_file`
  (plus `runbook` / `log_level`) are now accepted at the config root —
  `harness: codex` == `llm: {harness: codex}`. Both forms work (top-level wins on
  conflict); `junior init` writes the flat form. Other group fields still nest.
- **New `junior config list`** (top-level alias **`junior list`**). Discovery
  surface for runbook and harness, rounding out the config-inspection trio (`config list`
  = what exists, `config show` = their fields, `config env` = their env vars):
  lists registered runbooks + harnesses with one-line descriptions, marks your
  configured default (`*`). Harnesses show a two-part status: **install state** (`✓ installed` /
  `✗ not installed (pip install 'junior[...]')`, located via `find_spec` — never
  imported, so listing is fast even for heavy harnesses) and, when installed,
  **readiness** from the harness's new optional `Harness.is_ready()` env/CLI
  self-check (`ready` / `not ready: <why>`). Filter with `junior list runbooks`
  / `junior list harnesses`. Renders via rich (`src/junior/cli/listing.py`).
- **Harness modules lazy-import their heavy deps.** `pydantic`/`deepagents` now
  import `pydantic_ai` / `deepagents` + LangChain inside `complete()` (not at
  module top level), mirroring the runbook lazy-import rule. Importing a harness
  module — for `junior list`, `config show`, registry scans — is now cheap
  (deepagents dropped ~5s → ~0.2s), and `is_ready()` runs without pulling them.
- **`junior config init`** is now the canonical setup command (all config CRUD
  under `config`: `show`/`env`/`path` read, `init` writes). `junior init` stays as
  a top-level alias. The wizard walks (with an explanation per step) through:
  config location (**global** `~/.config/junior/settings.yaml` or **local**
  `./.junior.yaml`), runbook, harness, model, the `publish` toggle (platform
  runbooks only), and an optional output file — saved as YAML.
- **Config files are YAML only.** JSON config support is removed at every file
  level: auto-discovery is `.junior.{yaml,yml}` (project) and
  `~/.config/junior/settings.{yaml,yml}` (global); `junior init` writes
  `settings.yaml`; `--config FILE` / `--config -` expect YAML. (Data dumps —
  `junior dry-run -o ctx.json` and run records — stay JSON.)
- **Config hardening:** env now overrides nested config-file group fields
  (`HARNESS` beats a file's `llm.harness`); unknown top-level config keys log a
  warning (`ignoring unknown config key 'harness' — did you mean llm.harness?`).

#### Migration

| Before | After |
|--------|-------|
| `~/.config/junior/settings.json` (JSON config) | `~/.config/junior/settings.yaml` (`junior init` rewrites it) |
| `{"review": {"backend": "codex"}}` (JSON) | `llm:`<br>`  harness: codex` (YAML) |
| `--backend codex` / env `BACKEND=codex` | `--harness codex` / env `HARNESS=codex` (old names: deprecated alias) |
| `junior run --publish` (auto platform) | `junior run --runbook github_pr_review --publish` (or `gitlab_pr_review`) |
| `--platform gitlab` | `--runbook gitlab_pr_review` |
| relies on `GITLAB_TOKEN` auto-detecting the platform | set `runbook: gitlab_pr_review` explicitly (CLI/config/env) |
| flat `.junior.yaml` `backend: codex` (silently ignored) | nested `llm:`<br>`  harness: codex` |

### Lean core, per-backend extras

The core install no longer bundles every backend's SDK. `pip install junior` now ships
only the CLI, config, and the default `claudecode` backend (which drives the `claude`
CLI and needs no Python LLM SDK). Each other backend and platform is its own extra, and
extras compose: `junior[codex,pydantic,gitlab]`.

#### What changed

- **`pydantic-ai-slim[anthropic,openai]` moved out of core** into the new `pydantic`
  extra. The heavy anthropic+openai SDK tree is only installed when you actually use the
  `pydantic` backend.
- **`httpx` moved out of core** into the `github` extra (its only user is the GitHub
  collector/publisher).
- **New extras:** `pydantic`, `github`, `bitbucket`, `claudecode` (empty marker),
  and `codex` now carries `openai` (the strict-schema helper codex needs).
- **A bare install runs reviews out of the box** with `claudecode` — no regression for
  the default path.

#### Migration

| If you use… | Install |
|-------------|---------|
| default `claudecode` | `junior` (unchanged) |
| `--harness pydantic` | `junior[pydantic]` |
| `--harness codex` | `junior[codex]` |
| `--harness deepagents` | `junior[deepagents]` |
| GitHub PR metadata / publish | `junior[github]` |
| GitLab MR metadata / publish | `junior[gitlab]` (unchanged) |
| Bitbucket DC PR metadata / publish | `junior[bitbucket]` |
| everything | `junior[all]` (now also pulls `github` + `bitbucket` + `codex`) |

CI using the prebuilt Docker images is unaffected (extras are baked in). A GitHub Actions
job that `uv tool install`s junior for the `pydantic` backend must switch to
`junior[pydantic]`.

### YAML configs, stdin, file:// prompts

Junior reads YAML configs as a first-class citizen, can take a config from stdin,
and uses a single `context.prompts` list whose entries can be inline text or
`file://...` URIs.

#### What changed

- **YAML support.** `.junior.yaml` / `.junior.yml` / `--config foo.yaml` work
  the same as their `.json` counterparts. When multiple extensions coexist in
  the same directory, YAML wins.
- **`--config -`** reads YAML from stdin.
- **Unified `context.prompts`.** One `list[str]`; each entry is inline prompt
  text or a `file://path.md` URI. Relative `file://` URIs are resolved against
  the config file's own directory (or CWD for stdin/CLI), so multiple presets
  in `.junior/*.yaml` can each say `file://./prompts/foo.md`.
- **`context.prompt_files` removed.** Move paths into `context.prompts` as
  `file://...` URIs.
- **`PROMPT_FILES` env var removed.** Same migration.
- **`--prompt-file FILE`** kept as CLI sugar; it converts the path to an
  absolute `file://...` URI and appends to `context.prompts`.
- **Global config renamed:** `~/.config/junior/config.json` →
  `~/.config/junior/settings.{yaml,yml}`. Rename the file once; no
  auto-migration. Project-local file stays `.junior.{yaml,yml}`.

#### Migration

| Before | After |
|--------|-------|
| `~/.config/junior/config.json` | `mv ~/.config/junior/config.json ~/.config/junior/settings.yaml` |
| `{"context": {"prompt_files": ["prompts/security.md"]}}` | `{"context": {"prompts": ["file://prompts/security.md"]}}` |
| `PROMPT_FILES='["~/.junior/team.md"]'` | `PROMPTS='["file:///home/me/.junior/team.md"]'` |
| `junior run --prompt-file foo.md` | unchanged (sugar still works) |

### Prompts as user input

Junior ships no built-in prompts. It's a transparent wrapper: you supply the LLM
instructions, Junior just plumbs them through.

#### What changed

- **Removed** the `--prompts NAMES` flag, `PROMPTS_DIR` env var, `context.prompts_dir`
  config field, and the bundled `src/junior/prompts/*.md` files.
- **Added** `--prompt TEXT` — inline prompt text, repeatable. Each `--prompt` becomes one
  Prompt the LLM sees.
- **`--prompt-file FILE`** kept (still repeatable). No name-based lookup; the file path is
  the address.
- **Config shape:** `context.prompts: list[str]` — each entry is inline text or a
  `file://...` URI.
- **Merge semantics:** CLI `--prompt` / `--prompt-file` *append* to config values — config
  holds the baseline, CLI adds ad-hoc on top.
- **Empty is OK:** if neither CLI nor config provides a prompt, the LLM still gets the diff,
  MR metadata, prior discussion, and project instructions from `AGENT.md` / `AGENTS.md` /
  `CLAUDE.md`. No error.
- **Reference prompts** live in `examples/prompts/` in the docs site (`security.md`,
  `logic.md`, `design.md`, `docs.md`, `common.md`). Copy what you need — they're not
  auto-loaded.
- **Wizards:** `junior init` no longer asks about prompts. `junior run -i` no longer has a
  "prompts" step. Prompts are CLI/config only.

#### Migration

| Before | After |
|--------|-------|
| `junior run --prompts security,logic` | `junior run --prompt-file security.md --prompt-file logic.md` |
| `junior run --prompts common` | `junior run --prompt-file common.md` |
| `PROMPTS_DIR=~/.junior/prompts junior run --prompts my_rules` | `junior run --prompt-file ~/.junior/prompts/my_rules.md` |

### Config refactor + Typer CLI

The CLI is organised around verbs (`junior` alone shows help — no implicit default
action), and settings are grouped into nested classes that map to the runbook phases.

#### CLI: subcommand split

| Command | Replaces |
|---------|----------|
| `junior run [opts]` | bare `junior` (with all runbook flags) |
| `junior dry-run [opts]` | `--dry-run` (also `-o ctx.json` replaces the old `--collect` / `context` command) |
| `junior init` / `junior config init` | `--init` |
| `junior config show` | `--show-config` |
| `junior config path` | new — prints where config files live |

Other CLI changes:

- Migrated from `argparse` to **Typer**. Rich help with options grouped by panel (Context /
  Review / Output / Operational); each subcommand surfaces only its relevant panels.
- Shell completion built in: `junior --install-completion` (bash/zsh/fish/PowerShell).
- `--config` and `--publish` no longer overload "no-arg vs with-arg":
  - **`--config FILE`** (global option) — load this YAML config file.
  - **`junior run --publish`** — run the runbook's custom publish.
  - **`junior run --publish-file FILE`** — skip the runbook, publish a pre-generated `.md`.
- `--review CONTEXT_FILE` renamed to **`junior run --from-file CONTEXT_FILE`** — symmetric
  with `junior dry-run -o ctx.json`.
- Global options (`--config`, `-v`, `--version`) live on the parent and must be placed
  **before** the subcommand: `junior --config foo.yaml run ...`.

#### Breaking changes

- **Removed `--provider` / `MODEL_PROVIDER`.** Encode the provider in `--model`:
  `--model anthropic:claude-opus-4-6` (explicit), or `--model gpt-5.4-mini` (provider
  inferred from `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`).
- **Renamed env vars:** `AGENT_BACKEND` → `BACKEND` (now `HARNESS`), `MODEL_NAME` → `MODEL`,
  `PUBLISH_OUTPUT` → `OUTPUT_FILE`.
- **Settings API**: fields moved into groups — `settings.agent_backend` →
  `settings.llm.harness`, `settings.publish_output` → `settings.output.output_file`,
  `settings.ci_project_dir` → `settings.context.project_dir`, etc. Custom extensions need
  updating.

#### Internal

- `ContextSettings`, `LLMSettings`, `OutputSettings` each load their own env vars
  via pydantic-settings; the composite `Settings` plugs them together.
- `SourceMode` and `LogLevel` are now `StrEnum`s with case-insensitive validation.
- `--model` validator rejects unsupported provider prefixes early.
- `save_global_config` deep-merges nested groups instead of clobbering siblings.

## 0.1.3 and earlier

See git history.
