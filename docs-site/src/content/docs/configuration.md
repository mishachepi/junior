---
title: "Configuration"
---

# Configuration

Settings come from config files (YAML), environment variables, and CLI flags.

**Priority** (highest wins): CLI flags → env vars → `--config FILE` (or `--config -` for stdin) → `.junior.{yaml,yml}` (project) → `~/.config/junior/settings.{yaml,yml}` (global)

Env vars override nested config-file group fields too — e.g. `HARNESS` beats a config file's `llm.harness`.

Configuration flags work through **one override channel: the environment.** Every scalar flag except the primary selectors is an alias for `--env KEY=VALUE` — `--model X` exports `MODEL=X` for the run, which is why flags beat both exported env vars (the export overwrites them) and config files, and why a flag's value is inherited by the harness subprocess and script-runbook commands. The two primary selectors, `--runbook` and `--harness`, stay process-local: they choose what *this* invocation runs and are never exported (a nested `junior run` inside a script-runbook command must not inherit them). `--env` itself supplies any var inline (repeatable); `junior config env` lists which vars your harness + runbook combination needs.

> [!NOTE]
> User-facing output goes to **stdout** as human-readable presentation (the review renders as pretty Markdown in a TTY, raw Markdown when piped or redirected), while errors, status, warnings, and structlog logs all go to **stderr**. stdout stays pipe-safe: `junior run > review.md` yields clean Markdown.

## Mental model: three groups + top-level

Junior settings split into three mutually-independent groups, plus a couple of top-level keys (`runbook`, `log_level`):

| Group | What it controls |
|-------|------------------|
| **Context** | What to review — source mode, prompts, extra instructions, MR metadata |
| **LLM** | How to call the model — harness, model, API keys, system prompt, runtime limits |
| **Output** | Where to send — local file path, `publish` toggle, platform tokens, CI vars |

In a config file the three groups are nested explicitly under `context:` / `llm:` / `output:`, with `runbook:`, `log_level:` and `local_runbooks:` at the top level. In env vars they are flat — the *names* are the field names uppercased (`HARNESS`, `MODEL`, `SOURCE`, `PUBLISH`, `RUNBOOK`, `LOCAL_RUNBOOKS`, …) plus industry-standard aliases (`GITLAB_TOKEN`, `CI_*`, `GITHUB_*`, `ANTHROPIC_API_KEY`) and not prefixed with the group.

> **`local_runbooks`** (top-level, default `false`). Opt-in: load runbooks from `<project>/.junior/runbooks/` (see [adding runbooks](adding_backends.md#4-repo-local-in-juniorrunbooks)). It executes Python shipped in the repo, so enable it only in repos you trust.

> [!NOTE]
> **Deprecated alias:** `--backend` / env `BACKEND` and the config key `backend` are accepted as a deprecated alias for `harness` (kept for one version). Prefer `harness` / `HARNESS` / `--harness`.

> [!TIP]
> **Top-level shorthands.** The run-shaping knobs you set most often — `harness`, `model`, `publish`, `output_file` (plus `runbook` and `log_level`) — may live at the config **root** as shorthand. `harness: codex` is exactly `llm: {harness: codex}`; `output_file: review.md` is `output: {output_file: review.md}`. Both forms work; if you write both in one file the top-level value wins. `junior init` writes the flat form.

> [!WARNING]
> **Other group fields must be nested.** A flat top-level scalar that isn't a shorthand — e.g. `source: staged` (instead of `context: {source: staged}`) — is *ignored*, and Junior logs `ignoring unknown config key 'source' — did you mean context.source?`.

## Config files

Junior config files are YAML. Auto-discovery prefers `.yaml` over `.yml` when both exist in the same place.

| File | Scope | Created by |
|------|-------|-----------|
| `~/.config/junior/settings.{yaml,yml}` | Global (all projects) | `junior init` (choose "global") writes `settings.yaml` |
| `.junior.{yaml,yml}` | Project-local — found in the current directory or any parent up to the repo root (the first directory containing `.git`), so running junior from a subdirectory sees the same config | `junior init` (choose "local"), or by hand |
| `--config FILE` | Explicit override — any path, any name | Manual |
| `--config -` | Read YAML from stdin (CI / scripted runbooks) | n/a |

```bash
junior init                                       # interactive setup → global or local config
junior --config security.yaml run                 # explicit override
cat preset.yaml | junior --config - run           # from stdin
junior config path                                # show which files were found
```

A "preset" (e.g. *security checks only*) is just a YAML file you keep around and pass via `--config` — there is no special template registry. Project layouts often look like:

```
my-repo/
  .junior.yaml                # team default
  .junior/
    security.yaml             # ad-hoc preset, pass with --config .junior/security.yaml
    docs.yaml
    prompts/                  # files referenced via file://./prompts/...
      security.md
      docs.md
```

### YAML shape

```yaml
runbook: local_review                          # required: local_review, github_pr_review, gitlab_pr_review, bitbucket_pr_review
context:
  prompts:
    - file://./.junior/prompts/security.md      # path is relative to THIS config file
    - file://./.junior/prompts/logic.md
    - "Also flag any new TODO comments"         # inline text is fine too
  context_files:
    spec: SPEC.md
llm:
  harness: pydantic                             # the harness: claudecode (default), pydantic, codex, deepagents
  model: anthropic:claude-opus-4-6
  anthropic_api_key: sk-ant-...                 # prefer env var — see warning below
  max_file_size: 100000                         # skip files larger than this (bytes)
output:
  output_file: review.md
  publish: false                                # true → post to the runbook's platform
```

`file://...` URIs inside `context.prompts` are resolved against the config file's own directory at load time, so multiple presets in `.junior/*.yaml` can each reference `file://./prompts/foo.md` without ambiguity.

For the common case you don't need the groups at all — the run-shaping shorthands (`harness`, `model`, `publish`, `output_file`) sit at the root. This is what `junior init` writes:

```yaml
runbook: gitlab_pr_review
harness: pydantic
model: anthropic:claude-opus-4-6
publish: true
output_file: review.md
```

Reach for the `context:` / `llm:` / `output:` groups only when you need their other fields (prompts, API keys, `source`, `max_file_size`, CI vars, …). Tip: `junior config show --harness X --runbook Y` lists exactly which of those apply to your setup.

### Same thing as environment variables

```bash
export RUNBOOK=local_review
export PROMPTS='["file:///abs/path/security.md","Find security vulnerabilities"]'
export HARNESS=pydantic
export MODEL=anthropic:claude-opus-4-6
export ANTHROPIC_API_KEY=sk-ant-...
export MAX_FILE_SIZE=100000
export OUTPUT_FILE=review.md
export PUBLISH=false
```

> [!WARNING]
> **Keep API keys in env vars**
>
> Never commit `anthropic_api_key` / `openai_api_key` to a config file. The wizard does not write them, and they're listed as env vars only in this doc — the field exists in the schema for completeness, not as a recommendation.

## Variables table

### Group 1 — Context (what to review)

| Variable | CLI flag | Default | Description |
|----------|----------|---------|-------------|
| `SOURCE` | `--source` | `auto` | `auto`, `staged`, `commit`, `branch` |
| `BASE_SHA` | `--base-sha` | — | Diff against this commit. Wins over CI auto-vars |
| `PROJECT_DIR` (or `CI_PROJECT_DIR`) | `--project-dir` | `.` | Path to git repository |
| `INPUT_TEXT` | `[INPUT]` (positional) | — | Free-form task input handed to the runbook's collect step — the collector decides how to use it |
| `CI_MERGE_REQUEST_TARGET_BRANCH_NAME` | `--target-branch` | `main` | Target branch for diff |
| `PROMPTS` (JSON) | `--prompt TEXT` / `--prompt-file FILE` | `[]` | One list, each entry is inline text or `file://...`. JSON array in env (`PROMPTS='["..."]'`); CLI flags both append to config |
| `CONTEXT` (JSON) | `--context KEY="text"` | `{}` | Extra prompt instructions (KEY=text). Repeatable on CLI |
| `CONTEXT_FILES` (JSON) | `--context-file KEY=path` | `{}` | Data files to attach. Repeatable on CLI |
| `CI_MERGE_REQUEST_TITLE` | — | — | MR/PR title (auto-set by CI; passed to LLM) |
| `CI_MERGE_REQUEST_DESCRIPTION` | — | — | MR/PR description (auto-set by CI; passed to LLM) |
| `CI_MERGE_REQUEST_SOURCE_BRANCH_NAME` | — | — | Source branch name (auto-set by CI) |

### Group 2 — LLM (how to call the model)

Config key: `llm:`. The `harness` is how the LLM is invoked. The **runbook** (collect → render → LLM → publish, including the platform) is selected separately via the top-level `runbook` key.

| Variable | CLI flag | Default | Description |
|----------|----------|---------|-------------|
| `HARNESS` | `--harness` | `claudecode` | Harness: `claudecode`, `pydantic`, `codex`, `deepagents`, `pi` |
| `MODEL` | `--model` | per provider | Accepts `provider:model` (e.g. `anthropic:claude-opus-4-6`) or bare `model` |
| `OPENAI_API_KEY` | — | — | OpenAI API key |
| `ANTHROPIC_API_KEY` | — | — | Anthropic API key |
| `SYSTEM_PROMPT` (JSON) | — | `[]` | Role/identity layer merged on top of the runbook's own system prompt. Each entry is inline text or a `file://...` URI (like `context.prompts`) |
| `MAX_TOKENS_PER_AGENT` | — | `0` | Response token cap, 0 = no limit (`pydantic` harness only) |
| `MAX_FILE_SIZE` | — | `100000` | Skip file content above this size, bytes (collection + `pydantic`) |

> [!NOTE]
> `BACKEND` / `--backend` and the config key `backend` remain accepted as a deprecated alias for `HARNESS` / `--harness` / `harness` (kept for one version).

### Group 3 — Output (where to send)

| Variable | CLI flag | Default | Description |
|----------|----------|---------|-------------|
| `OUTPUT_FILE` | `-o` | — | Write review to file instead of stdout |
| `RECORD` | `--no-record` (to disable) | `true` | Write a machine-readable JSON run record to `<project_dir>/.junior/output/{timestamp}.json` after a successful run. Disable with `--no-record` or `output.record: false` |
| `PUBLISH` | `--publish` / `--no-publish` | `false` | Run the runbook's custom publish. `local_review` renders pretty Markdown locally; platform runbooks post to the PR/MR and require their tokens (see below). Without it, every runbook emits raw output instead |
| `GITLAB_TOKEN` | — | — | GitLab token with `api` scope |
| `GITHUB_TOKEN` | — | — | GitHub token |
| `CI_SERVER_URL` | — | `https://gitlab.com` | GitLab instance URL |
| `CI_PROJECT_ID` | — | — | GitLab project ID (auto-set by runner) |
| `CI_MERGE_REQUEST_IID` | — | — | MR number (auto-set by runner) |
| `CI_MERGE_REQUEST_DIFF_BASE_SHA` | — | — | Base SHA for inline comments (auto-set by runner) |
| `CI_COMMIT_BEFORE_SHA` | — | — | Previous HEAD on push events (auto-set by runner) |
| `CI_COMMIT_SHA` | — | — | Current commit SHA (auto-set by runner) |
| `GITHUB_REPOSITORY` | — | — | `owner/repo` format (auto-set by Actions) |
| `GITHUB_EVENT_NUMBER` | — | — | PR number (you may need to export this manually) |
| `GITHUB_EVENT_BEFORE` | — | — | Previous HEAD on push events (export from `${{ github.event.before }}`) |
| `BITBUCKET_URL` | — | — | Bitbucket Data Center base URL, e.g. `https://bitbucket.example.com` (HTTPS only) |
| `BITBUCKET_TOKEN` | — | — | Bitbucket DC HTTP access token (sent as a `Bearer` header) |
| `BITBUCKET_PROJECT` | — | — | Bitbucket project key |
| `BITBUCKET_REPO` | — | — | Bitbucket repository slug |
| `BITBUCKET_PR_ID` | — | — | Pull request id (set it in your CI — Bitbucket DC provides no pipeline vars) |

### Operational (top-level)

| Variable | CLI flag | Default | Description |
|----------|----------|---------|-------------|
| `RUNBOOK` | `--runbook` | — (required) | Which runbook to run: `local_review`, `github_pr_review`, `gitlab_pr_review`, `bitbucket_pr_review`, or `pkg.module:ClassName`. Selected explicitly — no auto-detection, no implicit default |
| `LOG_LEVEL` | `-v` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`. `-v` sets `DEBUG` |

> [!NOTE]
> Platform tokens and CI auto-vars are typically set as environment variables by the runner — you almost never list them yourself. See [CI Setup](ci.md).

## Variable details

### Picking a model — one flag for everything

`MODEL` (or `--model`) accepts two forms:

- **`provider:model`** — explicit provider, e.g. `anthropic:claude-opus-4-6`, `openai:gpt-5.4-mini`.
- **`model`** — provider is inferred from whichever API key is set (`OPENAI_API_KEY` → openai, `ANTHROPIC_API_KEY` → anthropic).

The legacy `--provider` flag is **removed** in 0.2.0 — encode it in `--model` instead.

```bash
junior run --model anthropic:claude-opus-4-6                   # explicit provider
junior run --model gpt-5.4-mini                                # provider from $OPENAI_API_KEY
ANTHROPIC_API_KEY=sk-ant-xxx junior run --harness pydantic     # default model for provider
```

### Harness reference

A **harness** is the LLM driver (`llm.harness` / `--harness` / env `HARNESS`). All five implement the same `complete()` call; they differ in how they reach a model and whether they read repo files themselves. Install only the one you run (`junior config list harnesses` shows install state + readiness; `junior config env` shows the vars below).

| Harness | Install | Reads files itself (`file_access`) | API key | Authenticates via |
|---------|---------|-----------------------------------|---------|-------------------|
| `claudecode` (default) | core — no extra | ✅ yes | optional — `ANTHROPIC_API_KEY` switches the CLI to API mode (`--bare`) | the `claude` CLI; run `claude` once to log in (Claude subscription) |
| `codex` | `junior[codex]` | ✅ yes | optional — `OPENAI_API_KEY` as fallback | the `codex` CLI; authenticate it once (OAuth) |
| `pydantic` | `junior[pydantic]` | ❌ no — diff is inlined | **required** — `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | a provider API key (matches your `--model` provider) |
| `deepagents` | `junior[deepagents]` | ❌ no — context is inlined | **required** — `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | a provider API key |
| `pi` | core — no extra | ✅ yes | per provider — or **none** for local models (`~/.pi/agent/models.json`) | the `pi` CLI; env key, `~/.pi/agent/auth.json`, or a local model |

- **`file_access`** — `claudecode`/`codex`/`pi` explore the repo with their own tools, so the runbook does **not** inline the full diff into the prompt. `pydantic`/`deepagents` get the diff inlined (they also have read-only file tools for extra exploration).
- **Honored config fields** — every API harness reads `llm.model` and `llm.max_file_size`; only `pydantic` additionally honors `llm.max_tokens_per_agent` (response-token cap). `claudecode`/`codex` ignore `model` unless you set it explicitly (the CLI picks otherwise).
- **No required env for the CLI harnesses** — `claudecode`/`codex` carry their own auth; `junior config env --harness pydantic` (or `deepagents`) lists the provider key. Setting both `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` is fine — pass `--model anthropic:...` / `--model openai:...` to disambiguate.

Per-harness deep dives: [Harnesses](agent_backends.md).

### Runbook reference

A **runbook** runs collect → render → LLM → publish, and the platform (local / GitHub / GitLab) is part of the runbook — not auto-detected from token presence. Pick one **explicitly** via the top-level `runbook` key, the `RUNBOOK` env var, or `--runbook` — with none set, `junior run` exits 2 (no implicit default). The code-review runbooks share one base and differ only in where they collect from and where they publish; `weather_advice` is a non-code example proving the framework generalizes.

| Runbook | Collects from | `needs_git` | `--publish` does | Required env (publish only) | Optional env |
|----------|---------------|-------------|------------------|------------------------------|--------------|
| `local_review` | local git diff | ✅ | renders pretty Markdown locally | — | — |
| `github_pr_review` | GitHub PR + diff | ✅ | posts PR review comments | `GITHUB_TOKEN`, `GITHUB_REPOSITORY`, `GITHUB_EVENT_NUMBER` | `GITHUB_EVENT_BEFORE` |
| `gitlab_pr_review` | GitLab MR + diff | ✅ | posts MR note + inline threads | `GITLAB_TOKEN`, `CI_PROJECT_ID`, `CI_MERGE_REQUEST_IID` | `CI_MERGE_REQUEST_DIFF_BASE_SHA`, `CI_COMMIT_SHA` |
| `bitbucket_pr_review` | Bitbucket DC PR + diff | ✅ | posts PR comment + inline comments | `BITBUCKET_URL`, `BITBUCKET_TOKEN`, `BITBUCKET_PROJECT`, `BITBUCKET_REPO`, `BITBUCKET_PR_ID` | — |
| `weather_advice` (example) | live weather (no git) | ❌ | prints a Rich terminal panel | — | — |

- **`needs_git`** — gates the preflight `.git` check. Code-review runbooks require a repo; `weather_advice` (and most local runbooks) run in any directory.
- **Honored config fields** — the code-review runbooks read `context.source`, `context.base_sha`, `context.target_branch`, and `llm.max_file_size`; `gitlab_pr_review` additionally reads `output.ci_server_url`, and `bitbucket_pr_review` reads `output.bitbucket_url`. `weather_advice` declares none.
- **Required env applies only when `--publish` is set** — without it, every runbook emits its raw output to stdout/`-o` and needs no token. Many `CI_*` / `GITHUB_*` vars are auto-provided by the CI runner; `junior config env --runbook X` lists exactly what your combination needs.
- Beyond these you can run an external runbook by import path (`--runbook pkg.module:ClassName`) or a repo-local one from `.junior/runbooks/` (opt-in `local_runbooks`). See [Adding runbooks & harnesses](adding_backends.md).

> [!NOTE]
> Setting both `GITLAB_TOKEN` and `GITHUB_TOKEN` is no longer an error — the runbook you select decides which one is used.

### Publishing

`output.publish: true` (or `--publish` / `--no-publish` to override) runs the runbook's custom publish instead of emitting the raw result. Each platform runbook validates its own targets when publishing — the required vars are in the runbook table above.

```bash
junior --config gh.yaml run --runbook github_pr_review --publish
RUNBOOK=gitlab_pr_review junior run --publish
```

### `BASE_SHA` / `--base-sha`

Anchor the diff at a specific commit (`SHA...HEAD`) in `auto` mode. Wins over every CI auto-var.

When unset, junior falls back to CI variables in this order, skipping the 40-zero placeholder GitLab/GitHub emit on first push:

1. `CI_MERGE_REQUEST_DIFF_BASE_SHA` — GitLab MR pipelines
2. `CI_COMMIT_BEFORE_SHA` — GitLab push events
3. `GITHUB_EVENT_BEFORE` — GitHub Actions push events (must be exported from `${{ github.event.before }}`)

This lets one `junior run --publish` step cover both MR/PR and push-to-main runbooks.

```bash
junior run --base-sha v1.2.0                 # everything since the v1.2.0 tag
junior run --base-sha $CI_COMMIT_BEFORE_SHA  # new commits in this push
```

### `PROMPTS` — where do prompts come from?

Junior ships no built-in prompts. You supply them three ways and they stack:

| Source | Shape | When |
|--------|-------|------|
| `--prompt TEXT` | Repeatable CLI flag | Ad-hoc tweaks for a single run |
| `--prompt-file FILE` | Repeatable CLI flag, `.md` files | Reusable instructions checked into the repo |
| Config | `context.prompts: list[str]` — each entry is inline text or a `file://...` URI | Stable baseline per project or globally |

CLI values **append** to config values — config holds the baseline, CLI adds extras on top. `--prompt-file FILE` is just a shortcut: it's converted to `file://<abs>` and merged into the same list.

`file://` URIs inside a config file are resolved against the config file's directory; URIs from `--prompt` / `--prompt-file` are resolved against the current working directory.

Example reference prompts live in [`examples/prompts/`](examples/prompts/) — copy them into your repo and reference the local copies.

```yaml
context:
  prompts:
    - file://./prompts/security.md      # next to this config file
    - "Find any new TODO comments"      # inline
```

```bash
junior run \
  --prompt "Quick smoke review for PR #123" \
  --prompt-file ./prompts/security.md
```

```bash
# Env-var form — JSON-encoded list
PROMPTS='["file:///abs/security.md","Quick smoke review"]' junior run
```

If no prompts come from any source, the LLM still gets the diff, MR metadata, prior discussion, project instructions from `AGENT.md` / `CLAUDE.md`, and code_review's built-in base rules (severity scale, focus on changed code).

### Tuning knobs (rarely changed)

- **`MAX_FILE_SIZE`** (default `100000`) — files larger than this have their content skipped; only the diff is included.
- **`MAX_TOKENS_PER_AGENT`** (default `0`, `pydantic` only) — response token cap; `0` = no limit.

### `OUTPUT_FILE` / `-o`

Write the rendered review to a local file. Independent from `--publish`: you can set both — `-o` always writes locally, `--publish` always posts to the platform.

```bash
junior run --prompt "Quick review" -o review.md
junior run -o review.md --publish     # both: file + platform
```

### Run record (`RECORD` / `--no-record`)

Every **successful** `junior run` writes a machine-readable, secret-free JSON record to `<project_dir>/.junior/output/{timestamp}.json`. It captures the runbook, harness, model, source, usage, errors, summary, blocking status, and the full structured output — handy for auditing, dashboards, or post-processing.

It's on by default. Disable it with the `--no-record` flag or `output.record: false` (field `OutputSettings.record`, default `true`). The `.junior/output/` directory should be gitignored.

```bash
junior run                # writes .junior/output/2026-06-06T12-00-00.json
junior run --no-record    # no record written
```
