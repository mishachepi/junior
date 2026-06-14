---
title: "CLI Reference"
---

# CLI Reference

Junior is a Typer app with subcommands. `junior` alone shows help — the canonical verb for the runbook is `junior run`.

## Commands

| Command | What it does |
|---------|--------------|
| [`junior run`](#junior-run) | Run the selected runbook end-to-end: collect → AI review (harness) → publish (writes a run record unless `--no-record`) |
| [`junior dry-run`](#junior-dry-run) | No-AI inspector: preview the full run (plan, collected context, exact system prompt + user message). `-o FILE` also saves the context JSON for `run --from-file` |
| [`junior runs`](#junior-runs) | Browse run records (the audit trail): `runs` lists recent ones, `runs last` prints the newest record's JSON (pipe-safe) |
| [`junior config init`](#junior-config-init) | Interactive setup wizard — config location (global/local), runbook, harness, publish & output → YAML (`junior init` is an alias) |
| [`junior config list`](#junior-config-list) | List available runbooks + harnesses (descriptions, your default, install state + readiness). Filter: `list runbooks` / `list harnesses`. `junior list` is an alias |
| [`junior config show`](#junior-config) | Print your current effective config as YAML + status header (config source, harness readiness) |
| [`junior config env`](#junior-config-env) | Env vars a harness + runbook need (required/optional, set/unset) |
| [`junior config path`](#junior-config) | Locate config files |

Global options live on the parent command (apply to any subcommand):

| Option | Description |
|--------|-------------|
| `--config FILE` | Load this YAML config (overrides `.junior.{yaml,yml}` and global config). Use `--config -` to read YAML from stdin |
| `-v`, `--verbose` | Enable debug logging. Works either side of the subcommand: `junior -v run` or `junior run -v` |
| `--version` | Show version and exit |
| `--install-completion` | Install shell completion (bash/zsh/fish/PowerShell) |
| `--show-completion` | Print completion script for manual install |
| `-h`, `--help` | Show help for any command |

Position: global options come **before** the subcommand: `junior --config foo.yaml run --harness pydantic`. (`-v`/`--verbose` is the exception — it also works *after* the subcommand: `junior run -v`.)

> [!NOTE]
> User-facing output goes to **stdout** as human-readable presentation (a pretty Markdown render in a TTY, raw Markdown when piped or redirected); errors, status, warnings, and structlog logs go to **stderr**. So stdout stays pipe-safe — `junior run > review.md` yields clean Markdown.

---

## `junior run`

Run a runbook: collect → AI review → output. The runbook is always an explicit choice — `--runbook`, env `RUNBOOK`, or config `runbook:` (set by `junior init`); with none of them set, `junior run` exits 2. There is no magic platform auto-detection — to post to a PR/MR you select the matching runbook and pass `--publish`.

```bash
junior run                                                            # your configured runbook → stdout
junior run --prompt "Find security issues"                           # inline prompt
junior run --runbook local_review "def f(uid): return q(uid)"        # review pasted text, no git needed
junior run --prompt-file rules.md --prompt "Focus on the new code"   # file + inline
junior run --runbook github_pr_review --publish                     # post to the GitHub PR
junior run --runbook gitlab_pr_review --publish                     # post to the GitLab MR
junior run --runbook bitbucket_pr_review --publish                  # post to the Bitbucket DC PR
junior run --publish-file review.md --runbook github_pr_review      # skip runbook; post pre-generated .md
junior run --from-file ctx.json                                      # phase 2 only, on saved context
junior run -i                                                        # interactive wizard
```

`--runbook` and `--harness` are the **primary selectors** — they choose what this
invocation runs. Every other scalar option is an **alias for `--env KEY=VALUE`**: the
flag exports its env var for the run (`--model X` ≡ `--env MODEL=X`), so it carries
normal env precedence and is inherited by the harness subprocess and script-runbook
commands. Repeatable options (`--prompt`, `--context`, `--context-file`) instead
*append* to what the config already has.

### Options — Runbook (which runbook to run)

| Option | Default | Description |
|--------|---------|-------------|
| `--runbook NAME` | — (required via flag/env/config) | Which runbook to run: `local_review`, `github_pr_review`, `gitlab_pr_review`, `bitbucket_pr_review`, the example `weather_advice`, or `pkg.module:ClassName` for an external runbook. `junior config list` shows them all. env: `RUNBOOK` |

`local_review` reviews the local git diff; `github_pr_review` / `gitlab_pr_review` / `bitbucket_pr_review` collect from a PR/MR. **What `--publish` does is per-runbook** (see [Output: publish vs raw](#publish-vs-raw-output)): with `--publish` `local_review` renders pretty Markdown locally while the platform runbooks post to the PR/MR; without it, every runbook just emits its raw result.

### Options — Context (what to review)

| Option | Default | Description |
|--------|---------|-------------|
| `[INPUT]` | — | Free-form input text (positional) handed to the runbook's collect step — the collector decides how to use it: code_review reviews the text instead of a git diff (no git repo required), a collect-less script runbook takes it as the user message (over stdin) |
| `--project-dir PATH` | `.` | Path to git repository. Alias for `--env PROJECT_DIR=…` |
| `--source` | `auto` | Git-diff strategy (git-based runbooks): `auto`, `staged`, `commit`, `branch`. Alias for `--env SOURCE=…` |
| `--base-sha SHA` | — | Diff against this commit (overrides CI auto-vars). Alias for `--env BASE_SHA=…` |
| `--target-branch` | `main` | Target branch for diff. Alias for `--env TARGET_BRANCH=…` (CI auto-var: `CI_MERGE_REQUEST_TARGET_BRANCH_NAME`) |
| `--prompt TEXT` | — | Inline prompt text for the LLM. Repeatable. Appends to `context.prompts` |
| `--prompt-file FILE` | — | `.md` prompt file. Repeatable. Sugar for `--prompt file://<abs>` |
| `--context KEY="text"` | — | Extra prompt instructions. Repeatable |
| `--context-file KEY=path` | — | Data files to attach. Repeatable |
| `--from-file CONTEXT_FILE` | — | Skip phase 1; load pre-collected context JSON |

### Options — Review (how to review)

| Option | Default | Description |
|--------|---------|-------------|
| `--harness` | `claudecode` | `claudecode`, `pydantic`, `codex`, `deepagents`, `pi`. env: `HARNESS` |
| `--model` | per provider | `provider:model` (e.g. `anthropic:claude-opus-4-6`) or bare `model`. Alias for `--env MODEL=…` |

> [!NOTE]
> `--backend` / env `BACKEND` (and the config key `backend`) are accepted as a deprecated alias for `--harness` / `HARNESS` / `harness`, kept for one version.

### Options — Output (where to send)

| Option | Default | Description |
|--------|---------|-------------|
| `-o`, `--output-file FILE` | stdout | Where the **raw output** goes when not publishing (default stdout). `-o -` forces stdout, overriding an `output_file` from config. Alias for `--env OUTPUT_FILE=…` |
| `--no-record` | record on | Disable the JSON run record. By default a successful run writes a secret-free record to `<project_dir>/.junior/output/{timestamp}.json`. Alias for `--env RECORD=false` |
| `--publish` / `--no-publish` | config (`false`) | Run / skip the runbook's **custom publish** (post to platform, pretty render, …). Overrides `output.publish`: `--publish` forces on, `--no-publish` forces off. Alias for `--env PUBLISH=true\|false` |
| `--publish-file REVIEW_FILE` | — | Skip the runbook; just post this pre-generated `.md` via the chosen runbook's platform |

#### Publish vs raw output

Every runbook follows the same rule:

- **No `--publish`** (default): you get the **raw LLM result** — the structured output as JSON, unformatted — on **stdout**, or in the file given by `-o`. Pipe-/redirect-safe. (Run metadata — tokens, errors, blocking — is in the run record under `.junior/output/`.)
- **`--publish`**: the runbook's **custom publish** runs instead — `github_pr_review`/`gitlab_pr_review`/`bitbucket_pr_review` post to the PR/MR, `local_review` renders pretty Markdown, `weather_advice` prints a Rich panel, a script runbook runs its `publish` command. The raw output is **not** printed (it's still in the run record).

```bash
junior run                      # raw JSON → stdout
junior run -o result.json       # raw JSON → file
junior run --publish            # custom publish (post / pretty), raw hidden
junior run --no-publish         # force raw even if config sets publish: true
junior run -o -                 # force stdout even if config sets output_file
```

### Options — Operational

| Option | Description |
|--------|-------------|
| `-i`, `--interactive` | Walk through every flag with the current config pre-filled before launching |
| `--env KEY=VALUE` | Set an env var for this run (repeatable). Same precedence as an exported env var (explicit CLI flags still win); visible to settings, the harness subprocess, and script-runbook `collect`/`publish` commands. Pair with [`junior config env`](#junior-config-env) to see what the harness + runbook need: `junior run --runbook gitlab_pr_review --publish --env GITLAB_TOKEN=… --env CI_PROJECT_ID=42` |

### Source modes (`--source`)

| Mode | Git command | When to use |
|------|------------|-------------|
| `auto` | smart detection | Default — works everywhere |
| `staged` | `git diff --cached` | Before committing |
| `commit` | `git diff HEAD~1` | After commit, before push |
| `branch` | `git diff target_branch...HEAD` | All branch changes |

`auto` detection order (first non-empty wins):

1. `--base-sha` / CI auto-var base (see below)
2. Branch diff (`target_branch...HEAD`) when not on target branch
3. Remote branch (`origin/target_branch...HEAD`) — auto-fetches if local ref missing
4. Uncommitted changes (`git diff HEAD`)
5. Staged changes (`git diff --cached`)

If all empty, exits cleanly with "no changes found".

### `--base-sha` resolution order

`--base-sha` wins. Otherwise junior reads, in order, skipping the 40-zero placeholder that runners emit on first push:

1. `CI_MERGE_REQUEST_DIFF_BASE_SHA` (GitLab MR pipelines)
2. `CI_COMMIT_BEFORE_SHA` (GitLab push events)
3. `GITHUB_EVENT_BEFORE` (GitHub Actions push events — must be exported from `${{ github.event.before }}`)

This means a single `junior run --runbook <platform>_pr_review --publish` step works for MR/PR and push runbooks without if-branching.

### `--from-file CONTEXT_FILE`

Skip phase 1 and feed a pre-collected context (produced by `junior dry-run -o`) straight into the AI review. Useful for:

- Running phases 1 and 2 on **different machines** (collect locally, review on a CI runner with the API key).
- Debugging — inspect what the AI sees.
- Reproducibility — pin the input to phase 2.

```bash
junior dry-run -o ctx.json
# inspect / commit / ship ctx.json
junior run --from-file ctx.json --harness pydantic
```

### `-i`, `--interactive`

Pre-fills the current config as defaults; walks through runbook, harness, model, source, target branch, output target. Final confirmation, then runs the runbook in the same process. Prompts are *not* part of the wizard — pass them via `--prompt` / `--prompt-file` or set them in `context.prompts`. Nothing is saved — use `junior init` for that.

```bash
junior run -i
junior run -i --source staged    # source pre-selected, everything else prompted
```

---

## `junior dry-run`

The unified no-AI inspector. It mirrors `junior run`'s flags but never calls the LLM and never posts — it shows you exactly what the run *would* do, so you can validate config, prompts, and the collected diff before spending tokens. With `-o FILE` it also saves the collected context as JSON for `junior run --from-file`.

```bash
junior dry-run                                  # preview the run (no AI)
junior dry-run --harness pydantic --prompt "Find security issues"
junior dry-run -o ctx.json                      # also save context for --from-file
```

### What it prints

In order — the detail first, the summary last:

- **Context** — the collected context: the changed-files table (code-review runbooks) or a generic field dump (any other runbook).
- **System prompt** and **User message** — the *exact* strings the harness would receive, rendered using the selected harness's `file_access`. When `file_access=True` (e.g. `claudecode`, `codex`) the diff is **not** inlined — the harness reads files itself. When `file_access=False` (e.g. `pydantic`, `deepagents`) the diff **is** inlined into the user message.
- **Output schema** — the result model the harness must return, field by field with types and which are optional (e.g. `summary: str`, `outfit: list[OutfitItem] (optional)`).
- **Plan** (last) — the runbook name; the harness and its `file_access`; the model; the `publish` flag; the `record` flag; and the output-schema model name.

Progress/diagnostic logs (collection, prompt sizes, …) are at DEBUG — add `-v` to see them; they go to stderr, so the preview on stdout stays clean.

### Options

It accepts the same flags as `junior run`:

- Runbook: `--runbook`
- Context: `[INPUT]`, `--project-dir`, `--source`, `--base-sha`, `--target-branch`, `--context`, `--context-file`
- Review: `--harness`, `--model` (used to render the plan + pick `file_access` for the prompt preview)
- Prompts: `--prompt`, `--prompt-file`
- `--publish` (shown in the plan; nothing is posted)
- `-o`, `--output-file FILE` — also write the collected context as JSON (for `junior run --from-file`). Without it, the preview is printed and no file is written.

Either way there is no AI call.

> [!NOTE]
> `dry-run` works for any runbook: code-review contexts get the changed-files table, and any other runbook's context (e.g. `weather_advice`) is shown as a generic field dump. An empty context (nothing to review) is called out explicitly.

---

## `junior runs`

The read side of the run record: every `junior run` writes a secret-free JSON trace to `<project_dir>/.junior/output/{timestamp}.json`, and `junior runs` lets you browse them without digging through the directory.

```bash
junior runs                     # table of recent records, newest first
junior runs last                # newest record's raw JSON → stdout
junior runs last | jq .output   # pipe-safe: extract the review itself
junior runs ~/work/api          # records of another project dir
```

- `junior runs [list]` — table: timestamp, runbook, harness, tokens, blocking, per-runbook summary. Shows the latest 20.
- `junior runs last` — prints the newest record's JSON raw to stdout (logs stay on stderr).
- An optional `PROJECT_DIR` picks the project (default: current directory).

Exit code 2 when there are no records (or the target is unknown).

---

## `junior config list`

List the extension points you can plug into `--runbook` / `--harness`. It rounds out the config-inspection trio: `config list` shows *what exists*, [`config show`](#junior-config) *their config fields*, [`config env`](#junior-config-env) *their env vars*. No arguments prints both sections; `runbooks` / `harnesses` filters to one. Also available as the top-level alias **`junior list`**.

```bash
junior config list             # both sections   (alias: junior list)
junior config list runbooks   # just runbooks
junior config list harnesses   # just harnesses
```

For each entry it shows the name, a one-line description, and a `*` next to the one your config currently selects (override per run with `--runbook` / `--harness`). Runbook descriptions and harness metadata come from the registry, so installed plugins appear here too.

Harnesses carry a two-part status:

- **Install state** — `✓ installed` if the harness's extra is present, or `✗ not installed (pip install 'junior[...]')` if it isn't. Checked cheaply (the package is *located*, never imported), so listing is fast even for heavy harnesses.
- **Readiness** — only shown when installed. Each harness self-reports via an `is_ready()` env/CLI check: `ready`, or `not ready: <why>` (e.g. the `claude` CLI isn't on `PATH`, or no provider key is exported). A harness that implements no check shows just the install state.

So `✓ installed` answers "can I select it?" and the readiness half answers "will it actually run right now?". The exact env vars behind a `not ready` are listed by [`junior config env`](#junior-config-env).

```text
Runbooks
  local_review     *   review the local git diff → raw JSON, or --publish for Markdown
  github_pr_review     review a GitHub PR → post review comments
  gitlab_pr_review     review a GitLab MR → post a note + inline threads
  bitbucket_pr_review  review a Bitbucket DC PR → post a comment + inline comments

Harnesses
  claudecode   *   claude CLI subprocess (no API key)        ✓ installed · ready
  codex            codex CLI subprocess                      ✓ installed · ready
  pydantic         single structured call via pydantic-ai    ✓ installed · not ready: set OPENAI_API_KEY / ANTHROPIC_API_KEY
  deepagents       LangChain orchestrator + subagents        ✗ not installed (pip install 'junior[deepagents]')
```

---

## `junior config init`

Interactive setup wizard (also available as the top-level alias `junior init`). Each step explains what it configures and prompts for:

1. **Config location** — save to the **global** config (`~/.config/junior/settings.yaml`, your default everywhere) or a **local** project config (`./.junior.yaml`, this repo only — commit it to share with your team).
2. **Runbook** — `local_review` (diff → stdout/file), `github_pr_review` (PR → comments), `gitlab_pr_review` (MR → note), `bitbucket_pr_review` (PR → comments), or any installed plugin.
3. **Harness** — claudecode / codex (local CLI, no key) or pydantic / deepagents (LLM API, key from env).
4. **Model** — only for API harnesses; accepts `provider:model` or a bare model name.
5. **Publish** — only for platform runbooks: post the review automatically (default off).
6. **Output file** (optional) — write the review to a file instead of stdout (empty = stdout).

Review prompts are not part of `init` — supply them at run time via `--prompt` / `--prompt-file`, or by editing the `context.prompts` array in the config file (each entry is inline text or a `file://...` URI).

Writes the result to the chosen YAML file. **Deep-merges** with whatever is already there: keys you added by hand (`max_file_size`, custom `prompts`, …) are preserved.

API keys are not stored in the config file. The wizard reminds you which env var to export (`OPENAI_API_KEY` or `ANTHROPIC_API_KEY`).

```bash
junior config init     # canonical
junior init            # alias — identical behavior
```

For a one-shot interactive run *without* saving, use [`junior run -i`](#-i---interactive) instead.

---

## `junior config`

Configuration utilities.

### `junior config show`

Print your **current effective configuration** as YAML — and, because the header reports where it loaded from and whether the harness is ready, it doubles as a status view. There's no separate `junior status`.

With **no flags** it resolves the harness + runbook from your config (harness defaults to `claudecode`; the runbook has no default) and prints *their* `context:` / `llm:` / `output:` fields at your **real current values** — most group fields are harness- or runbook-specific (e.g. `ci_server_url` only for `gitlab_pr_review`, `max_tokens_per_agent` only for `pydantic`), and each harness/runbook declares its own, so plugins show up too. Pass **`--harness X`** / **`--runbook Y`** to inspect a different combination instead.

A comment header shows the live status (stripped by any YAML parser, so the body stays valid YAML you can pipe back into a config):

```text
# Junior — current effective config (YAML; header comments show live status).
# source:   ~/.config/junior/settings.yaml + .junior.yaml
# harness:  codex · ready
# runbook: local_review
runbook: local_review
harness: codex
...
```

`source` lists the config files that contributed (or `defaults (no config file)`); the `harness` line carries the same readiness check as [`config list`](#junior-config-list). Secrets (API keys, tokens) and CI auto-vars are never shown — those are env-only, see [`junior config env`](#junior-config-env).

```bash
junior config show                                    # your current setup + status
junior config show --harness pydantic --runbook gitlab_pr_review > .junior.yaml
```

### `junior config env`

Show the **environment variables a harness + runbook rely on** — API keys, platform tokens, CI vars — each marked required/optional and whether it's currently set. Defaults to your configured harness/runbook; override with `--harness` / `--runbook`.

```bash
junior config env                                   # for your current config
junior config env --harness pydantic --runbook github_pr_review
```

`claudecode` / `codex` need no env var (they use local CLI auth); `pydantic` / `deepagents` need `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`. `github_pr_review` needs `GITHUB_TOKEN` (+ `GITHUB_REPOSITORY`, `GITHUB_EVENT_NUMBER`); `gitlab_pr_review` needs `GITLAB_TOKEN` (+ `CI_PROJECT_ID`, `CI_MERGE_REQUEST_IID`); `bitbucket_pr_review` needs all of `BITBUCKET_URL`, `BITBUCKET_TOKEN`, `BITBUCKET_PROJECT`, `BITBUCKET_REPO`, `BITBUCKET_PR_ID` (Bitbucket DC has no pipelines, so nothing is auto-provided). Many `CI_*` / `GITHUB_*` vars are auto-provided by the CI runner.

### `junior config path`

Print where junior looks for config files and whether each one exists.

```bash
$ junior config path
Junior config files (first match in each row wins; later rows override earlier):
  global   /Users/me/.config/junior/settings.yaml
  local    (none — searched: .junior.yaml, .junior.yml)
```

Useful when debugging "why is my setting being ignored?"

---

## Shell completion

`junior` is a Typer app, so it ships with completion for `bash`, `zsh`, `fish`, and PowerShell:

```bash
junior --install-completion          # one-time install for your current shell
junior --show-completion             # print the script (e.g. for sourcing manually)
```

After install, tab completes subcommands, flag names, and enum values (e.g. `--source`).

---

## Examples

```bash
# Review the current branch (no task prompt: diff + AGENT.md + base rules)
junior run

# Inline prompts — repeatable
junior run --prompt "Check security issues" --prompt "Check error handling"

# File prompts — repeatable
junior run --prompt-file ./prompts/security.md --prompt-file ./prompts/logic.md

# Review staged changes only
junior run --source staged --prompt "Quick correctness check"

# Post to a GitHub PR (GITHUB_TOKEN, GITHUB_REPOSITORY, GITHUB_EVENT_NUMBER set)
junior run --runbook github_pr_review --publish

# Post to a GitLab MR (GITLAB_TOKEN, CI_PROJECT_ID, CI_MERGE_REQUEST_IID set)
junior run --runbook gitlab_pr_review --publish

# Post to a Bitbucket DC PR (BITBUCKET_URL/TOKEN/PROJECT/REPO/PR_ID set)
junior run --runbook bitbucket_pr_review --publish

# Save to file AND publish to the GitHub PR
junior run --runbook github_pr_review -o review.md --publish

# Pick a different harness with a prompt
junior run --harness codex --prompt "Find bugs"

# Run an external runbook by import path
junior run --runbook "mypkg.module:JiraReview"

# Load a preset from anywhere (no special "templates" registry)
junior --config .junior/security.yaml run

# Or pipe a generated config in
generate-junior-config.sh | junior --config - run

# Split collect and review across machines
junior dry-run -o ctx.json                              # machine A
junior run --from-file ctx.json --harness pydantic      # machine B

# Two-step: generate locally, publish later from CI
junior run -o review.md
junior run --runbook github_pr_review --publish-file review.md

# Provide domain context to the AI
junior run --context lang="Python 3.12, FastAPI" \
           --context team="strict on error handling" \
           --context-file lint_results=ruff.json

# Debug what would be reviewed
junior dry-run --source branch --target-branch develop

# One-time setup
junior init
junior config path        # verify it landed where you expected
```

---

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Run completed successfully |
| 1 | Blocking issues found (any critical finding or `request_changes` recommendation) |
| 2 | Configuration error |
| 3 | Runtime error (collection, AI, or publish failure) |

> [!TIP]
> Use exit code 1 in CI to fail runbooks on critical findings.
