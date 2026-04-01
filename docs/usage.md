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
# Review with Claude Code backend
junior --backend claudecode --prompts security

# Review staged changes only
junior --source staged --prompts logic

# Review last commit
junior --source commit --prompts security,logic -o review.md

# See what would be reviewed without running AI
junior --dry-run

# Collect context to JSON, review separately
junior --collect -o context.json
junior --review context.json --backend claudecode --prompts security

# Extra context for AI
junior --context lang="Python 3.12, FastAPI" --context team="Be strict on error handling"

# Extra data files
junior --context-file lint_results=ruff.json --context-file coverage=cov.json

# Custom prompt files
junior --prompt-file ./rules/api_standards.md --prompt-file ./rules/naming.md

# Debug logging
junior -v --prompts security
```

## GitLab CI

```yaml
code-review:
  stage: review
  image: registry.gitlab.com/mishachepi/junior-test-review/junior:pydantic
  variables:
    OPENAI_API_KEY: $OPENAI_API_KEY
    GITLAB_TOKEN: $GITLAB_BOT_TOKEN
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
| `--backend` | `pydantic` | Agent backend: `pydantic`, `claudecode`, `codex`, `deepagents` |
| `--provider` | auto-detect | Model provider: `openai`, `anthropic` |
| `--model` | per provider | Model name, e.g. `claude-sonnet-4-6`, `gpt-5.4-mini` |
| `--source` | `auto` | What to review: `auto`, `staged`, `commit`, `branch` |
| `--project-dir` | `.` or `CI_PROJECT_DIR` | Path to git repository |
| `--target-branch` | `main` or from CI env | Target branch for diff |
| `--prompts` | `security,logic,design` | Built-in prompt names, comma-separated |
| `--prompt-file FILE` | — | Extra .md prompt file. Repeatable |
| `--context KEY="text"` | — | Extra instructions for AI. Repeatable |
| `--context-file KEY=path` | — | Data files for context. Repeatable |
| `--dry-run` | — | Show what would be reviewed, without running AI |
| `--collect` | — | Collect only, save context as JSON (use with `-o`) |
| `--review FILE` | — | Load context from JSON, skip collect phase |
| `--publish` | false | Post review to GitLab/GitHub |
| `--no-review` | false | Skip AI review (collect only) |
| `-o FILE` | stdout | Write review to file |
| `-v, --verbose` | — | Enable debug logging |
| `--config [FILE]` | `.env` | Generate .env template (no arg) or load config file |

Review is **always** printed to stdout (or file with `-o`).
With `--publish`, review is **additionally** posted to the platform.

### Source modes

| Mode | Git command | Use case |
|------|------------|----------|
| `auto` | Smart detection: CI base, branch diff, or uncommitted | Default — works in CI and locally |
| `staged` | `git diff --cached` | Before committing |
| `commit` | `git diff HEAD~1` | After committing, before pushing |
| `branch` | `target_branch...HEAD` | Review all branch changes |

## Configuration

All settings can be set via environment variables, `.env` file, or `--config` file.
CLI flags take priority over env vars. Env vars take priority over `.env`.

```bash
junior --config > .env    # generate template, then edit
```

### AI Keys (one required)

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | For OpenAI models |
| `ANTHROPIC_API_KEY` | For Anthropic models |

### Platform Tokens (set only one)

| Variable | Description |
|----------|-------------|
| `GITLAB_TOKEN` | GitLab token with `api` scope |
| `GITHUB_TOKEN` | GitHub token |

### Tuning

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_BACKEND` | `pydantic` | `pydantic`, `claudecode`, `codex`, `deepagents` |
| `MODEL_PROVIDER` | auto-detect | `openai` or `anthropic` (auto-detected from API key) |
| `MODEL_NAME` | `gpt-5.4-mini` / `claude-opus-4-6` | LLM model identifier |
| `PROMPTS` | `security,logic,design` | Comma-separated prompt names |
| `SOURCE` | `auto` | `auto`, `staged`, `commit`, `branch` |
| `MAX_CONCURRENT_AGENTS` | `3` | Limit parallel sub-agents (rate limit protection) |
| `PUBLISH_OUTPUT` | — | Write review to file instead of stdout |

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Review completed |
| 1 | Blocking issues found (critical or multiple high-severity) |
| 2 | Configuration error |
| 3 | Runtime error |

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
| `claudecode` | All prompts in system prompt, claude reads files via tools |
| `codex` | All prompts concatenated, codex reads files via sandbox |
| `deepagents` | 1 subagent per prompt, orchestrator coordinates |

## Docker

```bash
docker build --target pydantic .   # pydantic backend (~500MB)
docker build --target codex .      # + codex CLI
docker build --target full .       # all backends
```
