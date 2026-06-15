---
title: "Glossary"
---

# Glossary

Junior has exactly two core concepts — **Runbook** and **Harness**. Everything else
(settings, models, the registry) is plumbing around them: field-level reference in
[Configuration](configuration.md), internals in [Architecture](architecture.md),
the *why* in [Philosophy](philosophy.md).

## Runbook

One **task domain** — the whole vertical for a kind of task: *collect context →
render it → run the harness → publish the result*. It owns its **context schema**
and **result schema** and implements the domain logic. Defined as an ABC,
`Runbook[Context, Result]`, in `src/junior/runbook/base.py`.

A runbook is selected explicitly (`--runbook NAME`, config `runbook:`, or env
`RUNBOOK`; required — there is no implicit default). It can come from any of four sources: a
built-in, a pip-installed plugin, a `module:ClassName` import path, or a
repo-local file in `.junior/runbooks/` (opt-in — Python or a plain
[YAML manifest](script_runbooks.md)); see
[Adding a runbook](adding_runbooks.md).

Output follows one rule for every runbook: **without `--publish`** the framework
emits `render_output()` — raw result JSON, pipe-safe — to stdout/`-o`; **with
`--publish`** the runbook's custom `publish()` runs instead.

Built-in runbooks (the code-review family shares `CodeReviewRunbook` and differs
only in `collect` + `_post_to_platform`):

| Runbook | `collect` from | `--publish` does | Publish requirements |
|----------|----------------|------------------|----------------------|
| `local_review` | local git diff | renders pretty Markdown locally | none |
| `github_pr_review` | GitHub PR + diff | posts PR review comments | `GITHUB_TOKEN`, `GITHUB_REPOSITORY`, `GITHUB_EVENT_NUMBER` |
| `gitlab_pr_review` | GitLab MR + diff | posts MR note + inline threads | `GITLAB_TOKEN`, `CI_PROJECT_ID`, `CI_MERGE_REQUEST_IID` |
| `bitbucket_pr_review` | Bitbucket DC PR + diff | posts PR comment + inline comments | `BITBUCKET_URL`, `BITBUCKET_TOKEN`, `BITBUCKET_PROJECT`, `BITBUCKET_REPO`, `BITBUCKET_PR_ID` |
| `weather_advice` (example) | live weather API (no git) | prints a Rich terminal panel | none |

`weather_advice` exists to prove the frame fits any domain — it's the template to
copy for a non-code-review runbook. Full per-runbook settings + env:
[Configuration → Runbook reference](configuration.md#runbook-reference).

## Harness

One **LLM driver** — a single way of calling a model. The name fits: `claudecode`,
`codex`, and `pi` are agentic CLIs, `pydantic` is an SDK driver — Junior
*harnesses* them rather than being the inference engine itself. **Schema-agnostic**:
its one method, `complete(*, system_prompt, user_message, output_schema, settings) →
LLMResult`, takes the output schema as a *parameter*, so the same harness serves
every runbook. The validated schema instance is what makes deterministic `publish`
possible — downstream code works with typed fields, never with free-form model text.
Defined as the `Harness` ABC in `src/junior/runbook/base.py`;
each harness module in `src/junior/harnesses/` exposes a module-level `HARNESS`
instance. Selected via `--harness` / `llm.harness` / env `HARNESS`.

Built-in harnesses:

| Harness | Install | `file_access` | API key | Runs via |
|---------|---------|---------------|---------|----------|
| `claudecode` (default) | core | ✅ reads files | optional (`ANTHROPIC_API_KEY` → API mode) | the `claude` CLI |
| `codex` | `junior[codex]` | ✅ reads files | optional (`OPENAI_API_KEY`) | the `codex` CLI |
| `pydantic` | `junior[pydantic]` | ❌ diff inlined | **required** (`OPENAI_API_KEY` / `ANTHROPIC_API_KEY`) | a single structured pydantic-ai call |
| `deepagents` ⚠️ deprecated | `junior[deepagents]` | ❌ context inlined | **required** (`OPENAI_API_KEY` / `ANTHROPIC_API_KEY`) | a LangChain orchestrator (unreliable — use `pydantic`) |
| `pi` | core | ✅ reads files | per provider — or none for local models | the `pi` CLI (incl. Ollama/LM Studio/vLLM) |

**`file_access`** is a `ClassVar[bool]` on the harness: `True` means it explores
the repository with its own tools, so the runbook doesn't have to inline the full
diff into the prompt (small diffs are inlined regardless); `False` means it only
sees what's in the message.

Full settings + env per harness:
[Configuration → Harness reference](configuration.md#harness-reference); per-harness
deep dives in [Harnesses](agent_backends.md).
