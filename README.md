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
# Generate config template, then edit with your API keys
junior --config > .env

# Review current repo
junior --target-branch main

# Review with specific prompts
junior --prompts security,logic

# Save to file
junior --target-branch main -o review.md

# Publish to GitLab (requires GITLAB_TOKEN + junior[gitlab])
junior --publish

# Publish to GitHub (requires GITHUB_TOKEN)
junior --publish
```

## How It Works

```
Collect (deterministic)  ->  AI Review  ->  Publish
------------------------    ----------    ------------
git diff + changed files    pydantic      stdout / file
commit messages             codex         GitLab MR notes
--context / --context-file  deepagents    GitHub PR comments
platform API metadata
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

  --config [FILE]            Generate .env template (no arg) or load config file
  --project-dir PATH         Git repo path (default: ".")
  --target-branch BRANCH     Diff target (default: "main")
  --prompts NAMES            Comma-separated: security, logic, design, docs, common
  --prompt-file FILE         Extra .md prompt file. Repeatable
  --context KEY="text"       Extra instructions for AI. Repeatable
  --context-file KEY=path    Data files for context. Repeatable
  --publish                  Post to GitLab/GitHub (auto-detected from tokens)
  --no-review                Skip AI review (collect only)
  -o, --output-file PATH     Write to file instead of stdout
  --version                  Show version
```

## Configuration

```bash
junior --config > .env    # generate template, then edit
```

All settings via env vars, `.env` file, or `--config FILE`.

When `--config FILE` is used, it **replaces** the default `.env` (not merged).
Env vars always take priority over any file.

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | OpenAI API key |
| `ANTHROPIC_API_KEY` | — | Anthropic API key |
| `MODEL_PROVIDER` | auto-detect | `openai` or `anthropic` (auto-detected from key) |
| `MODEL_NAME` | `gpt-5.4-mini` / `claude-opus-4-6` | LLM model identifier |
| `GITLAB_TOKEN` | — | GitLab token (api scope) |
| `GITHUB_TOKEN` | — | GitHub token |
| `AGENT_BACKEND` | `pydantic` | `pydantic`, `codex`, `deepagents` |
| `PROMPTS` | `security,logic,design` | Comma-separated prompt names |
| `PROMPTS_DIR` | — | Extra directory with custom .md prompts |
| `FAIL_ON_CRITICAL` | `false` | Exit code 1 on critical findings |
| `MAX_FILE_SIZE` | `100000` | Skip files above this size (bytes) |
| `PUBLISH_OUTPUT` | — | Write review to file instead of stdout |
| `LOG_LEVEL` | `DEBUG` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

## Docs

| Doc | Description |
|-----|-------------|
| [architecture.md](docs/architecture.md) | Pipeline flow, dispatch pattern, project structure |
| [usage.md](docs/usage.md) | Installation, CLI reference, prompts, CI setup |
| [agent_backends.md](docs/agent_backends.md) | Backend comparison |
| [adding_backends.md](docs/adding_backends.md) | How to add/remove backends |
| [prompt_injection.md](docs/prompt_injection.md) | Security: prompt injection risks |
| [ROADMAP.md](ROADMAP.md) | Planned features and known issues |
