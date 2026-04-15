# CI Setup

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

GitLab CI auto-provides the rest: `CI_PROJECT_ID`, `CI_MERGE_REQUEST_IID`, `CI_MERGE_REQUEST_DIFF_BASE_SHA`, `CI_PROJECT_DIR`, etc. No manual setup needed.

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
      - run: uv tool install "junior @ git+https://github.com/mishachepi/junior.git"
      - run: junior --publish
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_REPOSITORY: ${{ github.repository }}
          GITHUB_EVENT_NUMBER: ${{ github.event.pull_request.number }}
```

`GITHUB_REPOSITORY` is a standard Actions variable but is listed here for clarity. `GITHUB_EVENT_NUMBER` must be mapped manually from the event payload.

## Required CI variables

| Platform | Auto-provided | You must set |
|----------|--------------|--------------|
| GitLab CI | `CI_PROJECT_ID`, `CI_MERGE_REQUEST_IID`, `CI_MERGE_REQUEST_DIFF_BASE_SHA`, `CI_PROJECT_DIR`, `CI_MERGE_REQUEST_TARGET_BRANCH_NAME` | `GITLAB_TOKEN` + API key for your backend (see below) |
| GitHub Actions | `GITHUB_REPOSITORY` | `GITHUB_TOKEN`, `GITHUB_EVENT_NUMBER` + API key for your backend (see below) |

API key depends on backend: `pydantic`/`deepagents` require `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`. `claudecode` and `codex` don't need an API key (they use CLI auth). See [Configuration](configuration.md) for details.

## Docker

```bash
docker build --target pydantic .   # pydantic + gitlab (~500MB)
docker build --target codex .      # + codex CLI + Node.js
docker build --target full .       # all backends + all extras
```

No `claudecode` target — Claude Code CLI requires interactive auth and is better suited for local use.
