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
