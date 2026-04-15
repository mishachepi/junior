# Junior — AI Code Review Agent

AI-powered code review for GitLab MRs and GitHub PRs. Runs as CLI or in CI.

## How it works

```
Collect (deterministic)  →  AI Review       →  Publish
------------------------    ---------------    ------------
git diff + changed files    claudecode (CLI)   stdout / file
commit messages             pydantic (SDK)     GitLab MR notes
--context / --context-file  codex (CLI)        GitHub PR comments
platform API metadata       deepagents (LLM)
```

Junior  
1. collects code context (diffs, files, commits, metadata)
2. sends it to an AI backend for review
3. and publishes the results — to stdout, a file, or directly as MR/PR comments

## Install

```bash
# From GitHub (core: pydantic-ai + httpx + structlog)
uv tool install "junior @ git+https://github.com/mishachepi/junior.git"

# With GitLab support (adds python-gitlab)
uv tool install "junior[gitlab] @ git+https://github.com/mishachepi/junior.git"

# All extras (gitlab + deepagents + langchain)
uv tool install "junior[all] @ git+https://github.com/mishachepi/junior.git"
```

### Prerequisites

The default backend (`claudecode`) requires `claude` CLI:

```bash
npm install -g @anthropic-ai/claude-code
claude  # authenticate once
```

| Backend | Requires |
|---------|----------|
| `claudecode` (default) | `claude` CLI installed and authenticated |
| `pydantic` | `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` env var |
| `codex` | `codex` CLI installed and authenticated |
| `deepagents` | `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` env var + `junior[all]` |

## Quick start

```bash
# Review current changes (default: claudecode backend)
junior --prompts security

# Interactive setup — choose backend, save config
junior --init

# all defaults explicit
junior --backend claudecode --source auto --target-branch main --prompts security,logic,design .

# Review with pydantic backend
export OPENAI_API_KEY=sk-...
junior --backend pydantic --source staged --prompts security,logic,design

# Review last commit, save to file
junior --source commit -o review.md

# Dry run — see what would be reviewed
junior --dry-run
```

This will:

1. **Collect** — auto-detect changes: CI base SHA → branch diff → uncommitted → staged
2. **Review** — run review via Claude Code CLI (`claude -p`)
3. **Output** — print formatted review to stdout

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Review completed successfully |
| 1 | Blocking issues found (any critical finding or `request_changes` recommendation) |
| 2 | Configuration error |
| 3 | Runtime error (collection, AI, or publish failure) |

!!! tip
    Use exit code 1 in CI to fail pipelines on critical findings.
