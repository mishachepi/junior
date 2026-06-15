---
title: "CI Setup"
---

# Junior as a code-review tool in CI

Wire Junior into your pipeline and it reviews each merge request / pull request and
posts the result back as a comment — the same review you get locally, run by the CI
runner instead of you.

## How it works

One CI job runs one command:

```bash
junior run --runbook <platform>_pr_review --harness <driver> --publish
```

- **`--runbook`** picks the platform — `gitlab_pr_review`, `github_pr_review`, or
  `bitbucket_pr_review`. The platform is **never auto-detected**; you choose it.
  Junior collects the MR/PR diff + metadata + prior discussion, runs one review, and
  `--publish` posts a summary note plus inline comments back to the MR/PR.
- **`--harness`** picks the LLM driver. **Use `pydantic` in CI**: it's a single
  structured API call — predictable cost, no agentic wandering, needs only an API
  key. `claudecode`/`codex` rely on interactive CLI auth that's awkward on a runner.
- **`--publish`** is what posts back. Without it Junior just prints the raw JSON
  result (useful for a dry run).

You provide a **platform token** (to post) and an **LLM API key** (to think). CI
auto-provides the rest (project id, MR number, base SHA). See
[Required CI variables](#required-ci-variables).

## GitLab CI

The recommended setup: the review runs **only when you click the manual ▶ button**
on a merge-request pipeline — never automatically, so you never pay for a review you
didn't ask for:

```yaml
stages:
  - review

junior-review:
  stage: review
  image: $CI_REGISTRY_IMAGE/junior:pydantic   # your registry — see "Building the image"
  script:
    - junior run --runbook gitlab_pr_review --harness pydantic --publish
  rules:
    # On a merge-request pipeline the job shows a ▶ play button and runs ONLY
    # when clicked. allow_failure keeps it optional (never blocks the MR).
    - if: $CI_MERGE_REQUEST_IID
      when: manual
      allow_failure: true
    # Any other pipeline (branch push, tag, schedule): don't add the job at all.
    - when: never
  variables:
    GIT_DEPTH: 0   # full clone so base-SHA diffing has history (default is shallow 50)
```

Set two variables in **Settings → CI/CD → Variables** (masked; uncheck **Protected**
so they're available on feature branches):

| Variable | Value |
|----------|-------|
| `GITLAB_TOKEN` | `glpat-...` with `api` scope — to post the MR note |
| `OPENAI_API_KEY` | `sk-...` — or `ANTHROPIC_API_KEY`; `pydantic` auto-detects the provider from whichever key is set |

GitLab auto-provides the rest: `CI_PROJECT_ID`, `CI_MERGE_REQUEST_IID`,
`CI_MERGE_REQUEST_DIFF_BASE_SHA`, `CI_PROJECT_DIR`, `CI_MERGE_REQUEST_TARGET_BRANCH_NAME`.

> [!TIP]
> The `image` must contain Junior with the `pydantic` extra — build it from the
> [Dockerfile](#building-the-image) `--target pydantic` and push it to your project's
> Container Registry. `$CI_REGISTRY_IMAGE` is the GitLab-provided path to that registry;
> swap in any registry you publish to.

### Trigger patterns

GitLab can't express "only when the MR is *opened*" — a merge-request pipeline runs
on open **and** on every push to the MR's source branch. So the practical choices are:

**Manual button (above)** — `when: manual` + `allow_failure: true`. Runs only on click.

**Automatic on every MR pipeline** — drop `when: manual`:

```yaml
  rules:
    - if: $CI_MERGE_REQUEST_IID
    - when: never
```

**Restrict to MRs targeting a specific branch:**

```yaml
  rules:
    - if: '$CI_MERGE_REQUEST_IID && $CI_MERGE_REQUEST_TARGET_BRANCH_NAME == "main"'
      when: manual
      allow_failure: true
    - when: never
```

**Also review direct pushes to `main`** — add a branch rule; Junior diffs only the
new commits via `CI_COMMIT_BEFORE_SHA` (it filters the forty-zero "new branch"
sentinel and falls back to a branch/`HEAD~1` diff):

```yaml
  rules:
    - if: $CI_MERGE_REQUEST_IID
      when: manual
      allow_failure: true
    - if: $CI_COMMIT_BRANCH == "main"
```

### Pass extra context or pin a model

`--context-file` injects extra files into the review prompt; `--model` pins a model
(`provider:model`):

```yaml
  script:
    - |
      junior run \
        --runbook gitlab_pr_review --harness pydantic --publish \
        --context-file standards=docs/review-standards.md \
        --model anthropic:claude-sonnet-4-6
```

## GitHub Actions

```yaml
name: Code Review
on:
  pull_request:
    types: [opened, synchronize]
  workflow_dispatch:        # adds a manual "Run workflow" button

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

`--runbook github_pr_review` reviews the PR → posts comments. `GITHUB_REPOSITORY` is
a standard Actions variable (listed for clarity); `GITHUB_EVENT_NUMBER` and
`GITHUB_EVENT_BEFORE` must be mapped from the event payload — the latter lets Junior
diff only the new commits on a push.

> [!TIP]
> For a **manual-only** GitHub equivalent of the GitLab button, trigger on
> `workflow_dispatch` alone (drop the `pull_request` trigger) and pass the PR number
> as a workflow input.

## Bitbucket Data Center

Bitbucket DC has no built-in pipelines, so Junior runs as a step in whatever CI drives
your builds (Jenkins, Bamboo, TeamCity, …). The runner checks out the PR branch; Junior
diffs locally against the PR target (resolved from the API) and talks to the Bitbucket
DC REST API (1.0) for PR metadata and for posting comments. Nothing is auto-provided —
you set all five `BITBUCKET_*` variables yourself.

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
> `BITBUCKET_TOKEN` is a Bitbucket **HTTP access token** (repository or project scoped,
> with write permission to comment) — Junior sends it as an `Authorization: Bearer`
> header, so the instance must be reached over **HTTPS**; plain `http://` URLs are
> rejected when publishing. Basic auth is not supported.

With `--publish` Junior posts a summary comment plus inline comments anchored to the
diff (`lineType: ADDED` on the effective diff); an inline comment whose line falls
outside the diff degrades to a general comment carrying the `file:line` location.
Existing PR comments (including threads) are fetched into the review context, like
GitLab discussions.

## Required CI variables

| Platform | Auto-provided | You must set |
|----------|--------------|--------------|
| GitLab CI | `CI_PROJECT_ID`, `CI_MERGE_REQUEST_IID`, `CI_MERGE_REQUEST_DIFF_BASE_SHA`, `CI_PROJECT_DIR`, `CI_MERGE_REQUEST_TARGET_BRANCH_NAME` | `GITLAB_TOKEN` + an LLM API key |
| GitHub Actions | `GITHUB_REPOSITORY` | `GITHUB_TOKEN`, `GITHUB_EVENT_NUMBER` + an LLM API key |
| Bitbucket DC (any CI) | — (nothing is auto-provided) | `BITBUCKET_URL`, `BITBUCKET_TOKEN`, `BITBUCKET_PROJECT`, `BITBUCKET_REPO`, `BITBUCKET_PR_ID` + an LLM API key |

The **LLM API key** depends on the harness: `pydantic` needs `OPENAI_API_KEY` or
`ANTHROPIC_API_KEY` (with both set it uses OpenAI unless you pass `--model anthropic:…`).
`claudecode`/`codex` use CLI auth instead — see [Configuration](configuration.md).
`deepagents` is deprecated; don't use it in CI.

> [!TIP]
> On ephemeral runners the run record written to `.junior/output/` is discarded with
> the runner, so you can skip it with `--no-record` (or `output.record: false`).

## Building the image

The [Dockerfile](https://github.com/mishachepi/junior/blob/main/Dockerfile) has one
target per harness bundle. Each builds on a `uv` + Python base and installs only what
that harness needs:

| Target | Harnesses | What it installs |
|--------|-----------|------------------|
| `pydantic` | `pydantic` | `--extra gitlab --extra pydantic` (the CI default, ~500 MB) |
| `codex` | `codex` | `--extra gitlab --extra codex` + Node.js + the `@openai/codex` CLI |
| `full` | `pydantic` + `codex` + `pi` + `deepagents` | `--extra all` + Node.js + the `@openai/codex` and `@earendil-works/pi-coding-agent` CLIs |

```bash
# Build (stamp the version label from pyproject.toml):
docker build --target pydantic \
  --build-arg VERSION=$(grep -m1 '^version' pyproject.toml | cut -d'"' -f2) \
  -t registry.gitlab.com/<group>/<project>/junior:pydantic .

# Push to your platform's registry (referenced by image: in .gitlab-ci.yml):
docker login registry.gitlab.com -u <user> -p <glpat-with-write_registry>
docker push registry.gitlab.com/<group>/<project>/junior:pydantic
```

> [!IMPORTANT]
> **Build for the runner's CPU architecture.** GitLab.com shared runners are
> `linux/amd64`. If you build on Apple Silicon (`arm64`) the image won't run on the
> runner (`exec format error`). Add `--platform linux/amd64` (BuildKit emulates it via
> QEMU — slower, but correct):
> ```bash
> docker build --platform linux/amd64 --target pydantic -t …/junior:pydantic .
> ```

There's no `claudecode` target — the Claude Code CLI needs interactive auth, so it's
local-only. `pi` ships in every install but its harness needs the `pi` CLI on `PATH`,
which only the `full` target installs.
