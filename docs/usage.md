# Junior — Usage Guide

## Installation

```bash
# Default (pydantic backend)
uv tool install junior

# With GitLab support
uv tool install "junior[gitlab]"

# With all backends
uv tool install "junior[all]"

# From source
uv tool install "./junior_hackathon_edition[all]"
```

## Local Testing

```bash
# Collect only — no AI, prints diff stats
junior --project-dir ./my-repo --target-branch main --no-review

# AI review with config file
junior --project-dir ./my-repo --target-branch main --config my.env

# AI review with env vars
OPENAI_API_KEY=sk-... junior --target-branch main

# Save review to file
junior --target-branch main -o review.md

# Extra context for AI
junior --context lang="Python 3.12, FastAPI" --context team="Be strict on error handling"

# Extra data files
junior --context-file lint_results=ruff.json --context-file coverage=cov.json

# Custom prompt files
junior --prompt-file ./rules/api_standards.md --prompt-file ./rules/naming.md

# Select specific built-in prompts
junior --prompts security,logic
```

## GitLab CI

```yaml
code-review:
  stage: review
  image: registry.gitlab.com/mishachepi/junior-test-review/junior:pydantic
  variables:
    OPENAI_API_KEY: $OPENAI_API_KEY
    GITLAB_TOKEN: $GITLAB_BOT_TOKEN
    MODEL_PROVIDER: openai
  script:
    - junior --publish
  rules:
    - if: $CI_MERGE_REQUEST_IID
  allow_failure: true
```

Settings > CI/CD > Variables (uncheck **Protected** for feature branches):

| Variable | Value |
|----------|-------|
| `OPENAI_API_KEY` | `sk-...` (masked) |
| `GITLAB_BOT_TOKEN` | `glpat-...` with `api` scope (masked) |

## GitHub Actions

```yaml
name: Code Review
on:
  pull_request:
    types: [opened, synchronize]

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - run: uv tool install "junior[all]"
      - run: junior --publish
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_REPOSITORY: ${{ github.repository }}
          GITHUB_EVENT_NUMBER: ${{ github.event.pull_request.number }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

## CLI Reference

| Argument | Default | Description |
|----------|---------|-------------|
| `--version` | — | Show version and exit |
| `--config [FILE]` | `.env` | Path to .env config file. Without argument: print example config |
| `--project-dir` | `.` or `CI_PROJECT_DIR` | Path to git repository |
| `--target-branch` | `main` or from CI env | Target branch for diff |
| `--prompts` | `security,logic,design` | Built-in prompt names, comma-separated |
| `--prompt-file FILE` | — | Extra .md prompt file. Repeatable |
| `--context KEY="text"` | — | Extra instructions for AI. Repeatable |
| `--context-file KEY=path` | — | Data files for context. Repeatable |
| `--publish` | false | Post review to GitLab/GitHub |
| `--no-review` | false | Skip AI review (collect only) |
| `-o FILE` | stdout | Write review to file |

Review is **always** printed to stdout (or file with `-o`).
With `--publish`, review is **additionally** posted to the platform.

## Configuration

All settings can be set via environment variables, `.env` file, or `--config` file.

When `--config FILE` is used, it **replaces** the default `.env` (not merged).
Env vars always take priority over any file.

```bash
junior --config > .env    # generate template, then edit
```

### Required

| Variable | Description |
|----------|-------------|
| `MODEL_PROVIDER` | `openai` or `anthropic` (auto-detected from API key) |

### AI Keys (one required)

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | For `MODEL_PROVIDER=openai` |
| `ANTHROPIC_API_KEY` | For `MODEL_PROVIDER=anthropic` |

### Platform Tokens (set only one)

| Variable | Description |
|----------|-------------|
| `GITLAB_TOKEN` | GitLab token with `api` scope |
| `GITHUB_TOKEN` | GitHub token |

### Tuning

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_BACKEND` | `pydantic` | `pydantic`, `codex`, or `deepagents` |
| `MODEL_NAME` | `gpt-5.4-mini` / `claude-opus-4-6` | LLM model identifier |
| `PROMPTS` | `security,logic,design` | Comma-separated prompt names |
| `PROMPTS_DIR` | — | Extra directory with .md prompt files |
| `FAIL_ON_CRITICAL` | `false` | Exit 1 on critical findings |
| `MAX_FILE_SIZE` | `100000` | Skip files above this size (bytes) |
| `PUBLISH_OUTPUT` | — | Write review to file instead of stdout |
| `LOG_LEVEL` | `DEBUG` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

## Prompts

### Built-in prompts

| Name | Focus |
|------|-------|
| `security` | Auth bypass, injection, hardcoded secrets, weak crypto |
| `logic` | Edge cases, error handling, incorrect conditions, resource leaks |
| `design` | DRY/KISS/SRP, naming, optimization, config issues |
| `docs` | Documentation completeness for new features and changes |
| `common` | Comprehensive single-pass review (all categories) |

### Custom prompts

**Option 1**: Add .md files to `PROMPTS_DIR` and reference by name:

```bash
PROMPTS_DIR=~/.junior/prompts junior --prompts security,my_team_rules
```

**Option 2**: Pass files directly with `--prompt-file`:

```bash
junior --prompt-file ./rules/api.md --prompt-file ./rules/naming.md
```

Prompt files use frontmatter format:

```markdown
---
name: api-standards
description: API design rules for our team
---

You are an expert reviewing REST API code...
```

### How prompts are used per backend

| Backend | Behavior |
|---------|----------|
| `pydantic` | 1 parallel AI agent per prompt, results merged |
| `codex` | Compact metadata prompt, codex reads files via sandbox |
| `deepagents` | 1 subagent per prompt, orchestrator coordinates |

## Docker

```bash
docker build --target pydantic .   # pydantic backend (~500MB)
docker build --target codex .      # + codex CLI
docker build --target full .       # all backends
```
