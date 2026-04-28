# FAQ

## Which backend should I use?

**`claudecode`** (default) — uses Claude CLI, no API key needed. Reads files via tools, explores beyond the diff.
**`pydantic`** — parallel agents via API key. Cheapest (~5K tokens), structured output, good for CI.
**`codex`** — uses OpenAI Codex CLI, similar to claudecode.
**`deepagents`** — experimental. Very expensive (~88K tokens), sometimes unreliable.

See [Agent backends](agent_backends.md) for detailed comparison.

## Why did the review find nothing?

- Check your prompts: `--prompts security` won't catch design issues
- Use `--dry-run` to verify the diff isn't empty
- Try broader coverage: `--prompts security,logic,design`
- Smaller models miss more — try a larger model with `--model`

## Why is the review so expensive?

- `deepagents` uses ~17x more tokens than `pydantic`
- `claudecode` explores files via tools — 120-240K tokens per review
- Use `--prompts common` instead of `security,logic,design` (1 agent vs 3)
- Review smaller changes: `--source staged` or smaller MRs

## CI fails with exit code 1 — is that a bug?

No. Exit code 1 means blocking issues were found (critical severity or request_changes recommendation). Review the findings and either fix them or use `allow_failure: true` in CI config.

## `--publish` fails — what do I check?

1. Platform token: `GITLAB_TOKEN` (with `api` scope) or `GITHUB_TOKEN`
2. Platform env vars:
   - GitLab: `CI_PROJECT_ID`, `CI_MERGE_REQUEST_IID` (auto-set in CI)
   - GitHub: `GITHUB_REPOSITORY` (auto-set), `GITHUB_EVENT_NUMBER` (map from `${{ github.event.pull_request.number }}`)

In GitLab CI these are auto-provided. In GitHub Actions, `GITHUB_EVENT_NUMBER` must be mapped manually — see [CI Setup](ci.md).

## `common` vs `security,logic,design` — which is better?

With `pydantic` backend, `--prompts security,logic,design` runs 3 parallel agents (more thorough). `--prompts common` runs 1 agent covering everything (cheaper and faster). Three separate prompts find more issues; `common` is good for quick reviews or tight budgets.

## Can I add my own prompts?

Yes, two ways:

```bash
# Option 1: PROMPTS_DIR — reference by name
PROMPTS_DIR=~/.junior/prompts junior --prompts security,my_rules

# Option 2: --prompt-file — pass path directly
junior --prompt-file ./rules/api.md
```

See [Prompts](prompts.md) for format details.

## How do I review without publishing?

```bash
junior --source branch -o review.md    # generate locally, inspect
junior --publish review.md             # publish when ready
```

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
junior --source branch -o review.md   # generate locally, inspect first
junior --publish review.md            # post the summary as an MR note
```

### GitHub (github.com)

```bash
gh pr checkout <PR-number>           # or: git fetch + checkout manually
export GITHUB_TOKEN=ghp_...
export GITHUB_REPOSITORY=owner/repo
export GITHUB_EVENT_NUMBER=<PR number>
junior --source branch --publish
```

### Notes

- **Inline (per-line) comments are skipped locally.** GitLab needs `CI_MERGE_REQUEST_DIFF_BASE_SHA` and `CI_COMMIT_SHA` to anchor each finding to the diff. CI sets them; locally they're empty, so Junior posts a single summary note instead. Set both manually if you want inline comments:
  ```bash
  export CI_COMMIT_SHA=$(git rev-parse HEAD)
  export CI_MERGE_REQUEST_DIFF_BASE_SHA=$(git merge-base origin/master HEAD)
  ```
- For repeated runs, put the env vars into `.junior.json` (project-local) or `~/.config/junior/config.json` (global). Same keys work — `gitlab_token`, `ci_server_url`, etc.
