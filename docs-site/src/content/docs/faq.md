---
title: "FAQ"
---

# FAQ

## Which harness should I use?

`claudecode` (default) if you use Claude Code; `pydantic` for cheap predictable CI runs;
`codex` for the OpenAI stack; `pi` for local models; `deepagents` is experimental. The
full decision table is [Choosing a harness](agent_backends.md). The harness is
independent of the **runbook** (see below) — any harness serves any runbook. The old
`--backend` / `BACKEND` / `backend:` still work as deprecated aliases for `--harness`.

## Which runbook should I use?

The runbook picks the platform — collect → review → publish — and you choose it explicitly (`--runbook NAME`, config `runbook:`, or env `RUNBOOK`). There is no auto-detection and no implicit default: with nothing set, `junior run` exits 2.

- **`local_review`** — reviews your local git diff and writes raw output to stdout / `-o FILE`. `--publish` renders the review as pretty Markdown to stdout (no posting; redirect with `>` to save).
- **`github_pr_review`** — reviews a GitHub PR; posts comments with `--publish`. Needs `GITHUB_TOKEN`, `GITHUB_REPOSITORY`, `GITHUB_EVENT_NUMBER`.
- **`gitlab_pr_review`** — reviews a GitLab MR; posts a note with `--publish`. Needs `GITLAB_TOKEN`, `CI_PROJECT_ID`, `CI_MERGE_REQUEST_IID`.
- **`bitbucket_pr_review`** — reviews a Bitbucket Data Center PR; posts comments with `--publish`. Needs `BITBUCKET_URL`, `BITBUCKET_TOKEN`, `BITBUCKET_PROJECT`, `BITBUCKET_REPO`, `BITBUCKET_PR_ID`.

To post a review to a PR/MR:

```bash
junior run --runbook github_pr_review --publish    # GitHub PR
junior run --runbook gitlab_pr_review --publish    # GitLab MR
junior run --runbook bitbucket_pr_review --publish # Bitbucket DC PR
```

## Why did the review find nothing?

- Junior ships no *task* prompts — you pass them via `--prompt`, `--prompt-file`, or config. With none, the LLM sees the diff, the built-in reviewer role + base rules, and `AGENT.md`/`CLAUDE.md` only (see [the default review prompt](#whats-in-the-default-review-prompt)).
- Use `junior dry-run` to verify the diff isn't empty.
- Be specific: `--prompt "Find security vulnerabilities"` beats vague asks.
- Smaller models miss more — try a larger model with `--model`.

## Why is the review so expensive?

- Agentic harnesses (`claudecode`, `codex`, `deepagents`) explore the repo, so they use far more tokens than `pydantic`'s single structured call — switch harness if cost matters.
- Fewer/shorter prompts → a smaller system prompt and fewer response tokens.
- Review smaller changes: `--source staged` or smaller MRs.

## CI fails with exit code 1 — is that a bug?

No. Exit code 1 means blocking issues were found (critical severity or request_changes recommendation). Review the findings and either fix them or use `allow_failure: true` in CI config.

## `junior run --publish` fails — what do I check?

0. Runbook: posting to a PR/MR needs `--runbook github_pr_review`, `gitlab_pr_review`, or `bitbucket_pr_review`. On `local_review`, `--publish` just renders Markdown locally (no posting) — that always works.
1. Platform token: `GITLAB_TOKEN` (with `api` scope) or `GITHUB_TOKEN`
2. Platform env vars:
   - GitLab: `CI_PROJECT_ID`, `CI_MERGE_REQUEST_IID` (auto-set in CI)
   - Bitbucket DC: `BITBUCKET_URL`, `BITBUCKET_PROJECT`, `BITBUCKET_REPO`, `BITBUCKET_PR_ID` (set them in your CI)
   - GitHub: `GITHUB_REPOSITORY` (auto-set), `GITHUB_EVENT_NUMBER` (map from `${{ github.event.pull_request.number }}`)

In GitLab CI these are auto-provided. In GitHub Actions, `GITHUB_EVENT_NUMBER` must be mapped manually — see [CI Setup](ci.md).

## What's in the default review prompt?

The system prompt is just whatever a runbook's `system_prompt()` returns — it can be
absolutely anything. What follows is only the **built-in code-review default**; it's a
set of recommendations to the model, not a framework rule. Even with no `--prompt`, the
code-review runbooks build their system prompt from three parts:

1. **Role** — the runbook's one-line `SYSTEM_PROMPT` (a senior-code-reviewer line in
   `code_review/base.py`): review the diff in the context of the surrounding codebase,
   prioritise correctness / security / data-integrity / API-contract regressions.
2. **`BASE_RULES`** — review rules (report only confident issues, focus on the changed
   code, when to `request_changes` vs `approve`) and the **severity definitions**
   (critical / high / medium / low). Lives in `code_review/instructions.py`.
3. **Project instructions** — the first of `AGENT.md` → `AGENTS.md` → `CLAUDE.md` found
   at the repo root, inlined verbatim (truncated past 30k chars).

**Your prompts are added, not substituted.** `--prompt` / `--prompt-file` / `context.prompts`
are inserted between the role and the rules, so the assembled prompt is:

```
SYSTEM_PROMPT (role)  →  your prompts  →  BASE_RULES  →  project instructions
```

For the built-in code-review runbooks, the role and `BASE_RULES` are baked in (change them
only by editing the source). To control the **whole** system prompt instead of adding to
it, write a [YAML manifest](script_runbooks.md) (its `system_prompt` is exactly what you
provide) or your [own runbook](adding_runbooks.md). Inspect the assembled prompt for any
run with `junior dry-run`.

## Many small prompts vs one big prompt — which is better?

All prompts merge into a single system prompt for one LLM call ([details](prompts.md)).
Several focused prompts give the model clearer checklists; one combined prompt keeps
the call cheaper.

## How do I write my own prompts?

Three ways (CLI values append to config):

```bash
# Inline — repeatable
junior run --prompt "Check security" --prompt "Check error handling"

# File — repeatable, .md only
junior run --prompt-file ./rules/api.md --prompt-file ./rules/naming.md

# Config — single context.prompts list (inline text or "file://..." URI) in
# .junior.yaml, ~/.config/junior/settings.yaml, or any file passed via --config
```

See [`examples/prompts/`](examples/prompts/) for five reference prompts to copy. [Prompts](prompts.md) has format details.

## Can I feed extra context or prompts into a built-in runbook?

Yes — the built-in code-review runbooks (`gitlab_pr_review`, `github_pr_review`,
`bitbucket_pr_review`, `local_review`) all accept extra input without any code change:

- **`--context KEY="text"` / `--context-file KEY=path`** → injected into the **user
  message** as named facts (repeatable).
- **`--prompt "..."` / `--prompt-file f.md`** → merged into the **system prompt**
  (repeatable). See [Prompts](prompts.md).

```bash
junior run --runbook gitlab_pr_review --publish \
  --context ticket="JIRA-123: rate limiter" \
  --context-file standards=docs/review-standards.md \
  --prompt "Focus on concurrency and error handling"
```

To run a **script that builds context** and feed its output into a built-in runbook,
capture its stdout into `--context` (no custom runbook needed):

```bash
junior run --runbook gitlab_pr_review --publish \
  --context deps="$(./scripts/collect-deps.sh)"
```

## Can I modify a built-in runbook through YAML?

Not directly. A [YAML manifest](script_runbooks.md) defines a **new** runbook; there is
no `extends`/`base` key to patch a built-in's `collect`/`publish`. Your options:

- Pass script output via `--context` / `--context-file` (above) — usually enough.
- Write your own runbook: a YAML `ScriptRunbook` with its own `collect:` shell command,
  or a Python subclass of the code-review runbook overriding `collect`/`render`. See
  [Adding a runbook](adding_runbooks.md).

## Can I add MCP servers, extra tools, or plugins to the harness?

Not currently. Junior drives each agent CLI in a **locked-down deterministic mode** with
a fixed flag set — `claudecode` and `pi` get a restricted read-only tool allowlist, `pi`
explicitly disables extensions/skills/prompt-templates, and no `--mcp-config` is passed.
There is no config escape hatch to inject MCP/tools/plugins/settings. This is deliberate:
one predictable schema-validated call, not an open agentic session. `codex` is the
exception — it reads its own `~/.codex/config.toml` (including any MCP servers configured
there). Configurable per-harness tools/MCP (passed through when a harness runs inside the
Junior Docker image) is a planned feature — see the project ROADMAP.

## How do I review without publishing?

```bash
junior run --source branch --publish > review.md   # render Markdown locally, inspect
junior run --runbook github_pr_review --publish-file review.md   # post that .md when ready (or gitlab_pr_review)
```

`--publish-file` expects a rendered Markdown review, so generate it with `--publish` (a `-o` file holds raw JSON instead).

## Where does Junior save what it did?

Every successful `junior run` writes a **run record** to `<project_dir>/.junior/output/{timestamp}.json` — a secret-free JSON snapshot of the run: runbook, harness, model, token usage, errors, summary, blocking flag, and the structured review output. It's on by default; turn it off with `--no-record` or `output.record: false`. `.junior/` is gitignored, so records never get committed.

## Can I pipe the review into another tool?

Yes. Without `--publish`, stdout carries exactly one JSON document matching the
runbook's schema — status, progress, and logs all go to **stderr** — so
`junior run > review.json` or `junior run | jq .comments` captures only the result.
With `--publish` on `local_review` you get the human-readable Markdown instead.

## How do I tweak settings for a single run without editing config?

Use `junior run -i` (or `--interactive`). It walks you through harness, model, source, target branch, and output target with your current config as the default — press Enter to keep, type to override. Prompts are not part of the wizard (pass via `--prompt` / `--prompt-file` or set in config). Nothing is written to disk; the choices apply only to this run. Use `junior init` instead if you want to persist them.

## How do I review a remote MR locally?

You can review (and publish to) any GitLab MR or GitHub PR from your laptop — including self-hosted GitLab. In CI most of these variables are set automatically; locally you set them yourself.

### GitLab (gitlab.com or self-hosted)

**1. Clone the repo and check out the MR's source branch**

```bash
git clone <repo-url> && cd <repo>
git fetch origin "merge-requests/<IID>/head:mr-<IID>"
git checkout mr-<IID>
```

`<IID>` is the MR number (`/-/merge_requests/<IID>` in the MR URL). The fetch above works without knowing the source branch name.

**2. Find the project ID**

Either via the UI: open the project page → ID is shown under the project name (also under Settings → General → "Project ID").

Or via the API:

```bash
curl -s -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  "https://gitlab.example.com/api/v4/projects/<owner>%2F<repo>" | jq '.id'
```

**3. Set the env vars**

```bash
export GITLAB_TOKEN=glpat-...                          # api scope (read+write for --publish)
export CI_SERVER_URL=https://gitlab.example.com        # only needed for self-hosted; default is gitlab.com
export CI_PROJECT_ID=<numeric id from step 2>
export CI_MERGE_REQUEST_IID=<MR number>
export CI_MERGE_REQUEST_TARGET_BRANCH_NAME=master      # default is "main"
```

The token must be issued **on the same instance** you're targeting. A `gitlab.com` token won't work against a self-hosted instance and vice versa.

**4. Run**

```bash
junior run --source branch --publish > review.md   # render Markdown locally, inspect first
junior run --runbook gitlab_pr_review --publish-file review.md   # post the summary as an MR note
```

### GitHub (github.com)

```bash
gh pr checkout <PR-number>           # or: git fetch + checkout manually
export GITHUB_TOKEN=ghp_...
export GITHUB_REPOSITORY=owner/repo
export GITHUB_EVENT_NUMBER=<PR number>
junior run --runbook github_pr_review --source branch --publish
```

### Notes

- **Inline (per-line) comments are skipped locally.** GitLab needs `CI_MERGE_REQUEST_DIFF_BASE_SHA` and `CI_COMMIT_SHA` to anchor each finding to the diff. CI sets them; locally they're empty, so Junior posts a single summary note instead. Set both manually if you want inline comments:
  ```bash
  export CI_COMMIT_SHA=$(git rev-parse HEAD)
  export CI_MERGE_REQUEST_DIFF_BASE_SHA=$(git merge-base origin/master HEAD)
  ```
- For repeated runs, put the env vars into `.junior.yaml` (project-local) or `~/.config/junior/settings.yaml` (global). Same keys work — `gitlab_token`, `ci_server_url`, etc.
