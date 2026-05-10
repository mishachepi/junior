# Junior — AI Code Review Agent

AI-powered code review for GitLab MRs and GitHub PRs. Run locally as a CLI, or wire it into CI.

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

1. collects code context (diffs, files, commits, MR/PR metadata)
2. sends it to an AI backend for review
3. publishes the results — to stdout, a file, or directly as MR/PR comments

## Install

```bash
# Core (pydantic-ai + httpx + structlog)
uv tool install "junior @ git+https://github.com/mishachepi/junior.git"

# With GitLab support (recommended if you'll review GitLab MRs)
uv tool install "junior[gitlab] @ git+https://github.com/mishachepi/junior.git"

# All extras (gitlab + deepagents + langchain)
uv tool install "junior[all] @ git+https://github.com/mishachepi/junior.git"
```

### Prerequisites by backend

The default backend (`claudecode`) requires `claude` CLI installed and authenticated:

```bash
npm install -g @anthropic-ai/claude-code
claude  # authenticate once
```

| Backend | Requires |
|---------|----------|
| `claudecode` (default) | `claude` CLI installed and authenticated |
| `pydantic` | `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` |
| `codex` | `codex` CLI installed and authenticated |
| `deepagents` | `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` + `junior[all]` |

## Quick start — local

The fastest path: install, configure once, then run from the branch you want to review.

### 1. Configure (one-time)

```bash
junior --init
```

Interactive wizard that asks for backend, provider (if needed), and default prompts, then saves them to `~/.config/junior/config.json`.
API keys are not saved there; keep them in env vars. The wizard prints a short summary and next steps after saving.

### 2. Check out the branch you want to review

!!! warning "Run Junior from the branch with your changes"
    By default Junior diffs `<target-branch>...HEAD`. If `HEAD` is on `main`/`master`, the diff is empty and Junior exits with **«no changes found, nothing to review»**.

```bash
cd /path/to/your/repo
git checkout my-feature-branch       # the branch with your changes
```

### 3. Review

```bash
junior                            # full review with the defaults from --init
junior --prompts security         # focus on a single area
junior --dry-run                  # preview what would be reviewed (no AI call)
junior -o review.md               # save the review to a markdown file
```

Output goes to stdout by default. Use `-o FILE` to save it.

### 4. Publish (optional)

If your branch has an open MR/PR and you want Junior to post the review there:

```bash
junior --publish                                # full pipeline + post comments
junior -o review.md && junior --publish review.md   # two-step: review first, post later
```

For local publishing you need a platform token (`GITLAB_TOKEN` with `api` scope, or `GITHUB_TOKEN`) and a couple of platform variables. On GitLab, missing `CI_MERGE_REQUEST_DIFF_BASE_SHA` / `CI_COMMIT_SHA` means Junior still posts the summary note but skips inline comments. The full walkthrough — including self-hosted GitLab — is in the [FAQ: review a remote MR locally](faq.md#how-do-i-review-a-remote-mr-locally).

## What `--source` does

`--source` picks **which changes** Junior reviews. Default is `auto` and covers most cases.

| Mode | What it diffs | When to use |
|------|---------------|-------------|
| `auto` (default) | First non-empty: CI base → branch vs target → uncommitted → staged | Most cases, including CI |
| `branch` | `<target-branch>...HEAD` | All branch changes vs `main`/`master` |
| `commit` | `HEAD~1...HEAD` | Last commit only |
| `staged` | `git diff --cached` | What's about to be committed |

Pair with `--target-branch` to change what `branch`/`auto` diff against (default: `main`).

```bash
junior --source branch --target-branch develop
```

See [CLI reference](cli.md) for every flag.

## CI

Junior runs unchanged in GitLab CI and GitHub Actions — most variables are auto-populated. Ready-to-paste pipeline configs are in [CI Setup](ci.md).

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Review completed successfully |
| 1 | Blocking issues found (any critical finding or `request_changes` recommendation) |
| 2 | Configuration error |
| 3 | Runtime error (collection, AI, or publish failure) |

!!! tip
    Use exit code 1 in CI to fail pipelines on critical findings.
