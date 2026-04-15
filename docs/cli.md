# CLI Reference

## Arguments table

| Argument | Default | Description |
|----------|---------|-------------|
| `--version` | — | Show version and exit |
| `--backend` | `claudecode` | Agent backend: `claudecode`, `pydantic`, `codex`, `deepagents` |
| `--provider` | auto-detect | Model provider: `openai`, `anthropic` |
| `--model` | per provider | Model name, e.g. `claude-sonnet-4-6`, `gpt-5.4-mini` |
| `--source` | `auto` | What to review: `auto`, `staged`, `commit`, `branch` |
| `PROJECT_DIR` | `.` | Path to git repository (positional) |
| `--target-branch` | `main` | Target branch for diff |
| `--prompts` | `security,logic,design` | Prompt names, comma-separated |
| `--prompt-file FILE` | — | Extra .md prompt file. Repeatable |
| `--context KEY="text"` | — | Extra instructions for AI. Repeatable |
| `--context-file KEY=path` | — | Data files for context. Repeatable |
| `--config [FILE]` | — | Print config template or load JSON config file |
| `--init` | — | Interactive setup wizard |
| `--dry-run` | — | Show what would be reviewed, no AI |
| `--collect` | — | Collect only, save context as JSON |
| `--review FILE` | — | Load context from JSON, skip collect |
| `--publish [FILE]` | — | Post to GitLab/GitHub |
| `-o, --output-file FILE` | stdout | Write review to file |
| `-v, --verbose` | — | Enable debug logging |

## Arguments

### `--version`

Print version and exit.

```bash
junior --version
```

### `--backend`

Which AI backend runs the review. Each has different tradeoffs:

- **`claudecode`** (default) — single `claude -p` subprocess. Reads files via tools, sees beyond the diff. Requires `claude` CLI.
- **`pydantic`** — parallel sub-agents via pydantic-ai SDK. Cheapest, structured output. Requires API key.
- **`codex`** — single `codex exec` in sandbox. Requires `codex` CLI.
- **`deepagents`** — LLM orchestrator + subagents. Experimental, expensive.

```bash
junior --backend claudecode --prompts security
```

See [Agent Backends](agent_backends.md) for detailed comparison.

### `--provider`

Override model provider auto-detection. Normally detected from which API key is set (`OPENAI_API_KEY` → openai, `ANTHROPIC_API_KEY` → anthropic). Set explicitly when both keys are present.

```bash
junior --provider anthropic --model claude-sonnet-4-6
```

### `--model`

Override the default model. Default depends on provider: `gpt-5.4-mini` for openai, `claude-opus-4-6` for anthropic. Not used by `claudecode` (Claude CLI picks its own model) unless you want to override it.

```bash
junior --model gpt-5.4
```

### `--source`

What changes to review.

| Mode | Git command | When to use |
|------|------------|-------------|
| `auto` | smart detection | Default — works everywhere |
| `staged` | `git diff --cached` | Before committing |
| `commit` | `git diff HEAD~1` | After commit, before push |
| `branch` | `git diff target_branch...HEAD` | All branch changes |

```bash
junior --source staged --prompts logic    # review only staged changes
junior --source branch --target-branch develop   # branch diff vs develop
```

**`auto` detection order** (first non-empty wins):

1. CI base SHA (`base_sha...HEAD`) — when `CI_MERGE_REQUEST_DIFF_BASE_SHA` is set
2. Branch diff (`target_branch...HEAD`) — when not on target branch
3. Remote branch (`origin/target_branch...HEAD`) — auto-fetches if local ref missing
4. Uncommitted changes (`git diff HEAD`)
5. Staged changes (`git diff --cached`)

If all strategies return empty, junior exits with "no changes found".

### `PROJECT_DIR`

Path to git repository. Positional argument (no `--` prefix). Defaults to current directory.

```bash
junior ../my-project --prompts security    # review another repo
```

### `--target-branch`

Branch to diff against. Default: `main`. In CI, overridden by `CI_MERGE_REQUEST_TARGET_BRANCH_NAME`.

```bash
junior --source branch --target-branch develop
```

### `--prompts` and `--prompt-file`

Two ways to specify what to review for:

- `--prompts security,logic,design` — load built-in prompts by name. With `pydantic` backend, each prompt runs as a separate parallel agent.
- `--prompt-file ./rules/api.md` — load a custom .md file. Repeatable. Added on top of `--prompts`.

```bash
junior --prompts security                           # single focus
junior --prompts security,logic,design              # 3 parallel agents
junior --prompt-file ./rules/api.md --prompts logic  # custom + built-in
```

Built-in prompts: `security`, `logic`, `design`, `docs`, `common`. See [Prompts](prompts.md).

`PROMPTS_DIR` env var adds a directory to search — custom prompts there can be referenced by name in `--prompts`.

### `--context` and `--context-file`

Pass extra information to the AI alongside the code diff. Format: `KEY=VALUE`. Both are repeatable. Files are validated at startup — missing files cause exit code 2.

```bash
# Text instructions (appended to the user message)
junior --context lang="Python 3.12, FastAPI" --context team="Be strict on error handling"

# Data files (read and appended as raw text)
junior --context-file lint_results=ruff.json --context-file coverage=cov.json
```

### `--config`

Two modes:

- **No argument** — prints example config template to stdout and exits
- **With file** — loads that JSON config file (overrides local and global config)

```bash
junior --config                    # print template
junior --config project.json       # use custom config file
```

### `--init`

Interactive setup wizard. Prompts for backend, provider, API key, and prompts. Saves to `~/.config/junior/config.json`.

```bash
junior --init
```

### `--dry-run`

Show what would be reviewed without calling the AI. Prints: file count, diff size, branch info, per-file stats (+added/-removed lines). Useful to verify the diff before spending tokens.

```bash
junior --dry-run
junior --source branch --dry-run   # check branch diff before review
```

### `--collect` and `--review`

Split the pipeline into separate steps. Mutually exclusive.

- `--collect` runs Phase 1 only, saves `CollectedContext` as JSON
- `--review FILE` loads that JSON, runs Phase 2 (AI review) only

```bash
junior --collect -o context.json                          # Phase 1 → JSON
junior --review context.json --backend claudecode -o review.md  # Phase 2 → review
```

Useful for debugging (inspect the collected context) or running collect and review on different machines.

### `--publish`

Two modes:

- **No argument** — runs full pipeline (collect → review → publish to platform)
- **With file** — skips collect and review, reads the .md file and publishes directly

```bash
junior --publish                  # full pipeline + publish
junior --publish review.md        # publish pre-generated file only
```

Requires a platform token (`GITLAB_TOKEN` or `GITHUB_TOKEN`) and platform-specific CI variables. See [CI Setup](ci.md).

### `-o, --output-file`

Write review to file instead of stdout. `--publish` posts to the platform **in addition** to the local output, not instead of it.

```bash
junior -o review.md                           # save to file
junior -o review.md --publish                  # save + publish
```

### `-v, --verbose`

Sets log level to `DEBUG`. Shows: collected context details, prompt sizes, git commands, API calls, token usage per agent. Equivalent to `LOG_LEVEL=DEBUG`.

```bash
junior -v --prompts security
```

## Examples

```bash
# Review with Claude Code backend
junior --backend claudecode --prompts security

# Review staged changes only
junior --source staged --prompts logic

# Review last commit, save to file
junior --source commit --prompts security,logic -o review.md

# Collect context to JSON, review separately
junior --collect -o context.json
junior --review context.json --backend claudecode --prompts security

# Two-step: generate review, then publish
junior -o review.md
junior --publish review.md

# Extra context for AI
junior --context lang="Python 3.12, FastAPI" --context team="Be strict on error handling"

# Extra data files
junior --context-file lint_results=ruff.json --context-file coverage=cov.json

# Custom prompt files
junior --prompt-file ./rules/api_standards.md --prompt-file ./rules/naming.md

# Debug logging
junior -v --prompts security
```
