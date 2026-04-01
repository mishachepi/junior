# Junior — AI Code Review Agent

AI-powered code review for GitLab MRs and GitHub PRs. Runs as CLI or in CI.

## Install

```bash
uv tool install junior              # default (pydantic backend)
uv tool install "junior[gitlab]"    # + GitLab API support
uv tool install "junior[all]"       # all backends + gitlab
```

## Quick Start

```bash
# Review current changes with Claude Code
junior --backend claudecode --prompts security

# Review staged changes before committing
junior --source staged --backend pydantic --prompts logic

# Review last commit
junior --source commit --prompts security,logic -o review.md

# See what would be reviewed without running AI
junior --dry-run

# Collect context and review separately
junior --collect -o context.json
junior --review context.json --backend claudecode --prompts security

# Publish to GitLab/GitHub
junior --publish
```

## How It Works

```
Collect (deterministic)  ->  AI Review       ->  Publish
------------------------    ---------------    ------------
git diff + changed files    pydantic (SDK)     stdout / file
commit messages             claudecode (CLI)   GitLab MR notes
--context / --context-file  codex (CLI)        GitHub PR comments
platform API metadata       deepagents (LLM)
```

## CI

```yaml
# GitLab CI
code-review:
  stage: review
  image: registry.gitlab.com/your-org/junior:pydantic
  variables:
    OPENAI_API_KEY: $OPENAI_API_KEY
    GITLAB_TOKEN: $GITLAB_BOT_TOKEN
  script:
    - junior --publish
  rules:
    - if: $CI_MERGE_REQUEST_IID
  allow_failure: true
```

## CLI

```
junior [options]

  --backend BACKEND        Agent backend: pydantic, claudecode, codex, deepagents
  --provider PROVIDER      Model provider: openai, anthropic (auto-detected from key)
  --model MODEL            Model name, e.g. claude-sonnet-4-6, gpt-5.4-mini
  --source MODE            What to review: auto (default), staged, commit, branch
  --project-dir PATH       Git repo path (default: ".")
  --target-branch BRANCH   Diff target (default: "main")
  --prompts NAMES          Comma-separated: security, logic, design, docs, common
  --prompt-file FILE       Extra .md prompt file. Repeatable
  --context KEY="text"     Extra instructions for AI. Repeatable
  --context-file KEY=path  Data files for context. Repeatable
  --dry-run                Show what would be reviewed, without running AI
  --collect                Collect only, save context as JSON (use with -o)
  --review CONTEXT_FILE    Load context from JSON file, skip collect phase
  --publish                Post to GitLab/GitHub (auto-detected from tokens)
  --no-review              Skip AI review (collect only)
  -o, --output-file PATH   Write to file instead of stdout
  -v, --verbose            Enable debug logging
  --config [FILE]          Generate .env template (no arg) or load config file
  --version                Show version
```

## Configuration

```bash
junior --config > .env    # generate template, then edit
```

All settings via env vars, `.env` file, or `--config FILE`.
CLI flags take priority over env vars. Env vars take priority over `.env`.

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | OpenAI API key |
| `ANTHROPIC_API_KEY` | — | Anthropic API key |
| `MODEL_PROVIDER` | auto-detect | `openai` or `anthropic` (auto-detected from key) |
| `MODEL_NAME` | `gpt-5.4-mini` / `claude-opus-4-6` | LLM model identifier |
| `GITLAB_TOKEN` | — | GitLab token (api scope) |
| `GITHUB_TOKEN` | — | GitHub token |
| `AGENT_BACKEND` | `pydantic` | `pydantic`, `claudecode`, `codex`, `deepagents` |
| `PROMPTS` | `security,logic,design` | Comma-separated prompt names |
| `SOURCE` | `auto` | `auto`, `staged`, `commit`, `branch` |
| `MAX_CONCURRENT_AGENTS` | `3` | Limit parallel sub-agents (rate limit protection) |
| `PUBLISH_OUTPUT` | — | Write review to file instead of stdout |

Exit codes: 0=success, 1=blocking issues found, 2=config error, 3=runtime error.

## Docs

| Doc | Description |
|-----|-------------|
| [architecture.md](docs/architecture.md) | Pipeline flow, dispatch pattern, project structure |
| [usage.md](docs/usage.md) | Installation, CLI reference, prompts, CI setup |
| [agent_backends.md](docs/agent_backends.md) | Backend comparison |
| [adding_backends.md](docs/adding_backends.md) | How to add/remove backends |
| [prompt_injection.md](docs/prompt_injection.md) | Security: prompt injection risks |
| [ROADMAP.md](ROADMAP.md) | Planned features and known issues |
