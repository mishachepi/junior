# Junior — AI Code Review Agent

AI-powered code review for GitLab MRs and GitHub PRs. Runs as CLI or in CI.

## Install

```bash
# From GitHub
uv tool install "junior @ git+https://github.com/mishachepi/junior.git"
uv tool install "junior[gitlab] @ git+https://github.com/mishachepi/junior.git"
uv tool install "junior[all] @ git+https://github.com/mishachepi/junior.git"

# From local clone
git clone https://github.com/mishachepi/junior.git && cd junior
uv tool install .
```

### Prerequisites by backend

| Backend | Requires |
|---------|----------|
| `claudecode` (default) | `claude` CLI installed and authenticated |
| `pydantic` | `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` env var |
| `codex` | `codex` CLI installed and authenticated |
| `deepagents` | `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` env var |

## Quick Start

```bash
# Review current changes (default: claudecode backend)
junior --prompts security

# Interactive setup
junior --init

# Review with pydantic backend (requires API key)
export OPENAI_API_KEY=sk-...
junior --backend pydantic --source staged --prompts security,logic,design

# Review last commit, save to file
junior --source commit -o review.md

# See what would be reviewed without running AI
junior --dry-run

# Collect context, review separately, then publish
junior --collect -o context.json
junior --review context.json --backend claudecode --prompts security -o review.md
junior --publish review.md
```

## How It Works

```
Collect (deterministic)  ->  AI Review       ->  Publish
------------------------    ---------------    ------------
git diff + changed files    claudecode (CLI)   stdout / file
commit messages             pydantic (SDK)     GitLab MR notes
--context / --context-file  codex (CLI)        GitHub PR comments
platform API metadata       deepagents (LLM)
```

See [full documentation](docs/index.md) for CLI reference, configuration, CI setup, and more.

## Docs

| Doc | Description |
|-----|-------------|
| [CLI Reference](docs/cli.md) | All flags, source modes, examples |
| [Configuration](docs/configuration.md) | Env vars, API keys, tuning |
| [Prompts](docs/prompts.md) | Built-in and custom prompts |
| [CI Setup](docs/ci.md) | GitLab CI, GitHub Actions, Docker |
| [Architecture](docs/architecture.md) | Pipeline flow, dispatch pattern, project structure |
| [Agent Backends](docs/agent_backends.md) | Backend comparison and recommendations |
| [FAQ](docs/faq.md) | Common questions and troubleshooting |
| [ROADMAP.md](ROADMAP.md) | Planned features and known issues |
