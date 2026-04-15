# Configuration

Settings come from JSON config files, environment variables, and CLI flags.

**Priority** (highest wins): CLI flags → env vars → `--config FILE` → `.junior.json` (local) → `~/.config/junior/config.json` (global)

## Config Files

Junior reads JSON config files in order, merging them (lower priority provides defaults, higher priority overrides):

| File | Scope | Created by |
|------|-------|-----------|
| `~/.config/junior/config.json` | Global (all projects) | `junior --init` |
| `.junior.json` | Project-local (repo root) | Manual |
| `--config FILE` | Explicit override | Manual |

```bash
junior --init                    # interactive setup → global config
junior --config project.json     # override with specific file
```

### Examples

All keys work in JSON and as environment variables.

JSON config (`~/.config/junior/config.json`, `.junior.json`, or `--config FILE`):

```json
{
  "agent_backend": "pydantic",
  "anthropic_api_key": "sk-ant-...",
  "prompts": "security",
  "max_concurrent_agents": 1
}
```

Environment variables:

```bash
export AGENT_BACKEND=pydantic
export ANTHROPIC_API_KEY=sk-ant-...
export PROMPTS=security
export MAX_CONCURRENT_AGENTS=1
```


## Variables table

| Variable | CLI flag | Default | Description |
|----------|----------|---------|-------------|
| **AI Provider** | | | |
| `OPENAI_API_KEY` | — | — | OpenAI API key |
| `ANTHROPIC_API_KEY` | — | — | Anthropic API key |
| `MODEL_PROVIDER` | `--provider` | auto-detect | `openai` or `anthropic` |
| `MODEL_NAME` | `--model` | per provider | Model identifier |
| **Backend & Review** | | | |
| `AGENT_BACKEND` | `--backend` | `claudecode` | `claudecode`, `pydantic`, `codex`, `deepagents` |
| `PROMPTS` | `--prompts` | `security,logic,design` | Comma-separated prompt names |
| `PROMPTS_DIR` | — | — | Directory with custom .md prompt files |
| `SOURCE` | `--source` | `auto` | `auto`, `staged`, `commit`, `branch` |
| `MAX_FILE_SIZE` | — | `100000` | Skip file content above this size (bytes) |
| `MAX_CONCURRENT_AGENTS` | — | `3` | Limit parallel sub-agents (`pydantic` backend) |
| `MAX_TOKENS_PER_AGENT` | — | `0` | Token limit per sub-agent, 0 = no limit (`pydantic`) |
| `LOG_LEVEL` | `-v` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `PUBLISH_OUTPUT` | `-o` | — | Write review to file instead of stdout |
| **Platform Tokens** | | | |
| `GITLAB_TOKEN` | — | — | GitLab token with `api` scope |
| `GITHUB_TOKEN` | — | — | GitHub token |
| **GitLab CI** | | | auto-set in CI, see [CI Setup](ci.md) |
| `CI_PROJECT_ID` | — | — | GitLab project ID |
| `CI_MERGE_REQUEST_IID` | — | — | MR number |
| `CI_MERGE_REQUEST_TARGET_BRANCH_NAME` | `--target-branch` | `main` | Target branch for diff |
| `CI_MERGE_REQUEST_DIFF_BASE_SHA` | — | — | Base SHA for diff |
| `CI_COMMIT_SHA` | — | — | Current commit SHA |
| `CI_SERVER_URL` | — | `https://gitlab.com` | GitLab instance URL |
| **GitHub Actions** | | | auto-set in CI, see [CI Setup](ci.md) |
| `GITHUB_REPOSITORY` | — | — | `owner/repo` format |
| `GITHUB_EVENT_NUMBER` | — | — | PR number |

!!! note
    Platform tokens and CI variables are typically set as environment variables in CI. You can also put them in config files — the same keys work in JSON.

## Variable Details

### `OPENAI_API_KEY`

API key for OpenAI models. When set, auto-detects `MODEL_PROVIDER=openai` and `MODEL_NAME=gpt-5.4-mini`.

```bash
export OPENAI_API_KEY=sk-...
junior --backend pydantic --prompts security
```

### `ANTHROPIC_API_KEY`

API key for Anthropic models. When set, auto-detects `MODEL_PROVIDER=anthropic` and `MODEL_NAME=claude-opus-4-6`. For `claudecode` backend, enables API mode (`--bare`) instead of subscription.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
junior --backend pydantic --prompts security
```

**When is a key required?**

| Backend | API key | Without key |
|---------|---------|-------------|
| `claudecode` (default) | Optional — enables API mode (`--bare`) | Uses Claude subscription |
| `pydantic` | Required | Won't start |
| `codex` | Optional — fallback if not logged in | Uses `codex login` OAuth |
| `deepagents` | Required | Won't start |

Setting both keys is fine — set `MODEL_PROVIDER` explicitly to choose which one to use.

### `GITLAB_TOKEN`

GitLab personal access token with `api` scope. Enables GitLab collector (MR metadata from API) and publisher (MR notes + inline comments).

```bash
export GITLAB_TOKEN=glpat-...
junior --publish
```

### `GITHUB_TOKEN`

GitHub token. Enables GitHub collector (PR metadata from API) and publisher (PR comments + review comments).

```bash
export GITHUB_TOKEN=ghp_...
junior --publish
```

Set **only one** platform token — setting both is a validation error. Without either token, junior runs in local mode (stdout/file only). For `--publish` you also need CI platform variables — see [CI Setup](ci.md).

### `AGENT_BACKEND` / `--backend`

Backend for AI review. Default: `claudecode`.

```bash
junior --backend pydantic --prompts security
# or
export AGENT_BACKEND=pydantic
```

### `MODEL_PROVIDER` / `--provider`

Override auto-detection. Normally detected from API key: `OPENAI_API_KEY` → `openai`, `ANTHROPIC_API_KEY` → `anthropic`. Set explicitly when both keys are present.

```bash
junior --provider anthropic --model claude-sonnet-4-6
# or
export MODEL_PROVIDER=anthropic
```

### `MODEL_NAME` / `--model`

Override the default model. Default: `gpt-5.4-mini` (openai), `claude-opus-4-6` (anthropic). For `claudecode` backend, passed as `--model` to Claude CLI; if unset, Claude CLI picks its own default.

```bash
junior --model gpt-5.4
# or
export MODEL_NAME=gpt-5.4
```

### `PROMPTS` / `--prompts`

Comma-separated prompt names. Default: `security,logic,design`.

```bash
junior --prompts security,logic
# or
export PROMPTS=security,logic
```

### `PROMPTS_DIR`

Directory with custom `.md` prompt files. Prompts placed here can be referenced by name in `--prompts`, alongside built-in ones. No CLI flag.

```json
{"prompts_dir": "~/.junior/prompts"}
```

### `SOURCE` / `--source`

What to review: `auto` (default), `staged`, `commit`, `branch`.

```bash
junior --source branch
# or
export SOURCE=branch
```

### `MAX_FILE_SIZE`

Files larger than this (bytes) have their content skipped — only the diff is included. Default: `100000` (~100KB). No CLI flag.

```json
{"max_file_size": 200000}
```

### `MAX_CONCURRENT_AGENTS`

Limit parallel sub-agents in `pydantic` backend. Default: `3`. No CLI flag.

```json
{"max_concurrent_agents": 1}
```

### `MAX_TOKENS_PER_AGENT`

Response token limit per sub-agent. `pydantic` backend only. Default: `0` (no limit). No CLI flag.

```json
{"max_tokens_per_agent": 4096}
```

### `LOG_LEVEL` / `-v`

Logging verbosity. Default: `INFO`. The `-v` flag sets `DEBUG`.

```bash
junior -v --prompts security   # DEBUG level
# or
export LOG_LEVEL=DEBUG
```

### `PUBLISH_OUTPUT` / `-o`

Write review to file instead of stdout.

```bash
junior --prompts security -o review.md
# or
export PUBLISH_OUTPUT=review.md
```
