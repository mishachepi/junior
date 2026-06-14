---
title: "CI Setup"
---

# CI Setup

## GitLab CI

One job covers both MRs and direct pushes to `main` (for a push it diffs only the new
commits, via `CI_COMMIT_BEFORE_SHA`):

```yaml
code-review:
  stage: review
  image: registry.gitlab.com/mishachepi/junior-test-review/junior:pydantic
  script:
    - junior run --runbook gitlab_pr_review --harness pydantic --publish
  rules:
    - if: $CI_MERGE_REQUEST_IID
    - if: $CI_COMMIT_BRANCH == "main"
  variables:
    GIT_DEPTH: 0   # default shallow clone (50) hides CI_COMMIT_BEFORE_SHA
  allow_failure: true
```

`--runbook gitlab_pr_review` selects the GitLab runbook (review the MR → post a note);
`--publish` posts the result. The platform is never auto-detected — you choose it
explicitly. On the first push to a new branch GitLab sets `CI_COMMIT_BEFORE_SHA` to
forty zeros — junior filters this out and falls back to other strategies (branch diff,
HEAD~1).

Set two variables in Settings > CI/CD > Variables (masked; uncheck **Protected** for
feature branches) — they're automatically available to all jobs:

| Variable | Value |
|----------|-------|
| `OPENAI_API_KEY` | `sk-...` |
| `GITLAB_TOKEN` | `glpat-...` with `api` scope |

GitLab CI auto-provides the rest: `CI_PROJECT_ID`, `CI_MERGE_REQUEST_IID`, `CI_MERGE_REQUEST_DIFF_BASE_SHA`, `CI_PROJECT_DIR`, etc.

### Restrict to a specific target branch

```yaml
  rules:
    - if: '$CI_MERGE_REQUEST_IID && $CI_MERGE_REQUEST_TARGET_BRANCH_NAME == "main"'
```

### Pass extra context and set model

Use `--context-file` to inject additional files into the review prompt, and `--model` to pin a specific model:

```yaml
  script:
    - |
      junior run \
        --runbook gitlab_pr_review \
        --publish \
        --context-file key=path/to/file.md \
        --model <model-name>
```

## GitHub Actions

```yaml
name: Code Review
on:
  pull_request:
    types: [opened, synchronize]
  push:
    branches: [main]

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - run: uv tool install "junior[pydantic] @ git+https://github.com/mishachepi/junior.git"
      - run: junior run --runbook github_pr_review --harness pydantic --publish
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_REPOSITORY: ${{ github.repository }}
          GITHUB_EVENT_NUMBER: ${{ github.event.pull_request.number }}
          GITHUB_EVENT_BEFORE: ${{ github.event.before }}
```

`--runbook github_pr_review` selects the GitHub runbook (review the PR → post comments); `--publish` posts the result. `GITHUB_REPOSITORY` is a standard Actions variable but is listed here for clarity. `GITHUB_EVENT_NUMBER` and `GITHUB_EVENT_BEFORE` must be mapped manually from the event payload — the latter lets junior diff only the new commits in a push to `main`.

## Bitbucket Data Center

Bitbucket DC has no built-in pipelines, so junior runs as a step in whatever CI drives your builds (Jenkins, Bamboo, TeamCity, …). The runner checks out the PR branch; junior diffs locally against the PR target (resolved from the API) and talks to the Bitbucket DC REST API (1.0) for PR metadata and for posting comments. Nothing is auto-provided — you set all five `BITBUCKET_*` variables yourself.

A generic CI step (Jenkins declarative pipeline shown; any CI works the same way):

```groovy
stage('Code Review') {
  environment {
    BITBUCKET_URL     = 'https://bitbucket.example.com'   // HTTPS only
    BITBUCKET_TOKEN   = credentials('junior-bitbucket-token')
    BITBUCKET_PROJECT = 'PROJ'                            // project key
    BITBUCKET_REPO    = 'my-repo'                         // repository slug
    BITBUCKET_PR_ID   = "${env.CHANGE_ID}"                // PR id from your CI's PR trigger
    OPENAI_API_KEY    = credentials('openai-api-key')     // for the pydantic harness
  }
  steps {
    sh 'junior run --runbook bitbucket_pr_review --harness pydantic --publish'
  }
}
```

> [!NOTE]
> `BITBUCKET_TOKEN` is a Bitbucket **HTTP access token** (repository or project scoped, with write permission to comment) — junior sends it as an `Authorization: Bearer` header, so the instance must be reached over **HTTPS**; plain `http://` URLs are rejected when publishing. Basic auth is not supported.

With `--publish` junior posts a summary comment plus inline comments anchored to the diff (`lineType: ADDED` on the effective diff); an inline comment whose line falls outside the diff degrades to a general comment carrying the `file:line` location. Existing PR comments (including threads) are fetched into the review context, like GitLab discussions.

## Required CI variables

| Platform | Auto-provided | You must set |
|----------|--------------|--------------|
| GitLab CI | `CI_PROJECT_ID`, `CI_MERGE_REQUEST_IID`, `CI_MERGE_REQUEST_DIFF_BASE_SHA`, `CI_PROJECT_DIR`, `CI_MERGE_REQUEST_TARGET_BRANCH_NAME` | `GITLAB_TOKEN` + API key for your harness (see below) |
| GitHub Actions | `GITHUB_REPOSITORY` | `GITHUB_TOKEN`, `GITHUB_EVENT_NUMBER` + API key for your harness (see below) |
| Bitbucket DC (any CI) | — (nothing is auto-provided) | `BITBUCKET_URL`, `BITBUCKET_TOKEN`, `BITBUCKET_PROJECT`, `BITBUCKET_REPO`, `BITBUCKET_PR_ID` + API key for your harness (see below) |

API key depends on harness: `pydantic`/`deepagents` require `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`. `claudecode` and `codex` don't need an API key (they use CLI auth). See [Configuration](configuration.md) for details.

> [!TIP]
> `--harness` selects the LLM driver (the old `--backend` flag still works as a deprecated alias). On ephemeral CI runners the run record written to `.junior/output/` is discarded with the runner, so you can skip it with `--no-record` (or `output.record: false`).

## Docker

```bash
docker build --target pydantic .   # pydantic + gitlab (~500MB)
docker build --target codex .      # + codex CLI + Node.js
docker build --target full .       # all harnesses + all extras
```

No `claudecode` target — Claude Code CLI requires interactive auth and is better suited for local use.
