---
title: "Anatomy of a run"
---

# Anatomy of a run

A single run, traced end to end. This walkthrough follows the **code-review
runbook** reviewing a test repository full of intentional bugs — but the shape
is the same for *every* runbook: **collect → one structured LLM call → publish**.
Use it to see exactly what Junior gathers, what the model receives, and what
comes back out.

The full review output (all 38 findings, the formatted markdown) lives on the
next page: [Review output in detail](output.md).

## The command

```bash
OPENAI_API_KEY=sk-... junior run \
  --runbook local_review \
  --harness pydantic \
  --prompt-file ./prompts/security.md \
  --prompt-file ./prompts/logic.md \
  --prompt-file ./prompts/design.md \
  --source branch --target-branch main \
  --project-dir ../junior-test-repo \
  --publish > /tmp/junior_review_output.md
```

`--publish` makes `local_review` render the result as Markdown (Phase 5); the
redirect just saves it. Drop `--publish` and you get the raw `ReviewResult` JSON
on stdout instead — the [output contract](../cli.md) every runbook follows.

| Setting | Value |
|---------|-------|
| Collector | `local` (no platform API) |
| Harness | `pydantic` (single structured call) |
| Publisher | `local` (renders Markdown to stdout with `--publish`) |
| Model | `openai:gpt-5.4-mini` |
| Prompts | `security.md`, `logic.md`, `design.md` |

## The test repository

- **main**: one commit, just `hello.py` with a basic `greet()`.
- **feature/auth-system**: 2 commits adding an auth + database + API layer.

The diff under review — `feature/auth-system` vs `main`:

| File | Status | Lines |
|------|--------|-------|
| `api.py` | added | +109 |
| `auth.py` | added | +103 |
| `database.py` | added | +120 |
| `hello.py` | modified | +53 |

**4 files, +385 lines.**

## Phase 1 — Collect

**`junior.collect.local`** → `collect.core.collect.collect_base()`: runs `git
diff`, parses changed files, reads commit messages, attaches any extra context.
The output is a `CollectedContext`:

```json
{
  "target_branch": "main",
  "commit_messages": [
    "feat: add authentication and database layer\n...",
    "feat: add API endpoints and integrate auth with greetings\n..."
  ],
  "full_diff": "<11,801 chars — unified diff of 4 files>",
  "changed_files": [
    {"path": "api.py",      "status": "added",    "diff": "<...>", "content": "<109 lines>"},
    {"path": "auth.py",     "status": "added",    "diff": "<...>", "content": "<103 lines>"},
    {"path": "database.py", "status": "added",    "diff": "<...>", "content": "<120 lines>"},
    {"path": "hello.py",    "status": "modified", "diff": "<...>", "content": "<58 lines>"}
  ],
  "extra_context": {}
}
```

The `local` collector has no platform API, so MR title/description/labels and
`source_branch` stay empty — git is the only source. Each `ChangedFile` carries
both its diff and full content.

## Phase 2 — Build the user message

**`junior.runbooks.code_review.render.build_user_message()`** turns the
`CollectedContext` into the markdown **user message** the model sees (here ~12.3k
chars):

```markdown
## Merge Request:
**Branches:**  → main

### Commits (2)
- feat: add authentication and database layer
- feat: add API endpoints and integrate auth with greetings

### Changed Files
- `api.py` (added)
- `auth.py` (added)
- `database.py` (added)
- `hello.py` (modified)

### Diff
```diff
<full unified diff — 385 added lines across 4 files>
```
```

`--context` / `--context-file` entries (none here) would appear in an
"Additional Context" section near the top.

## Phase 3 — Build the system prompt

**`junior.runbooks.code_review.instructions.build_review_prompt()`** assembles
one system prompt by concatenating these parts, blank-line separated
(`merge_prompts` in `prompt_loader.py`):

1. the runbook's `SYSTEM_PROMPT` role, plus the user's prompt bodies
   (`--prompt` / `--prompt-file`) — here `security.md`, `logic.md`, `design.md`;
2. the shared `BASE_RULES`.

The runbook does not inline `AGENT.md` / `AGENTS.md` / `CLAUDE.md` — a harness that
wants project memory reads it itself from its working directory (`claudecode` →
`CLAUDE.md`, `codex` → `AGENTS.md`).

There is no per-prompt fan-out: every body lands in the **same** system prompt,
and the pydantic harness makes **one** structured call.

```
[ SYSTEM_PROMPT + security + logic + design ] + BASE_RULES
                              │
              one system prompt  ✕  one user message (Phase 2)
                              │
                              ▼
                   single structured LLM call
```

## Phase 4 — The LLM review

**`junior.harnesses.pydantic`** makes one structured call with
`output_type=LLMReviewOutput`. The model returns `summary`, `recommendation`,
and the `comments` list directly. Junior then wraps that into a `ReviewResult`,
attaching the measured token usage:

```json
{
  "summary": "The code quality is poor overall, with multiple critical security flaws...",
  "recommendation": "request_changes",
  "comments": [/* 38 findings */],
  "input_tokens": 28174,
  "output_tokens": 7224,
  "tokens_used": 35398
}
```

| Severity | Count |
|----------|-------|
| 🔴 Critical | 5 |
| 🟠 High | 20 |
| 🟡 Medium | 13 |
| **Total** | **38** |

The full findings tables are on the [next page](output.md).

## Phase 5 — Publish

With `--publish`, **`junior.publish.local.post_review()`** →
`publish.core.formatter.format_summary()` renders the `ReviewResult` to Markdown
on stdout (here redirected to `/tmp/junior_review_output.md`). Without `--publish`,
`local_review` prints that same `ReviewResult` as raw JSON instead.

Every run also writes a secret-free JSON trace to
`<project_dir>/.junior/output/{timestamp}.json` (on by default; disable with
`--no-record`).

See the [rendered output](output.md#formatted-output) on the next page.

## The whole pipeline

```
git diff ──▶ collect.local ─────────▶ CollectedContext
                                          │
              render.build_user_message() ▼ ──▶ user message (~12KB markdown)
                                          │
       instructions.build_review_prompt() ▼ ──▶ system prompt (merged, ~4KB)
                                          │
                    pydantic harness call ▼ ──▶ LLMReviewOutput ─▶ ReviewResult (+tokens)
                                          │
       (--publish) format_summary() ▼ ──▶ Markdown
                                          │
                       local.post_review() ▼ ──▶ stdout
                                          ·
   (no --publish) raw ReviewResult JSON ─────▶ stdout / -o file
              .junior/output/{ts}.json trace ─▶ always written
```

Every runbook — GitLab, GitHub, Bitbucket, or your own — swaps the collector and
publisher but keeps this exact spine.
