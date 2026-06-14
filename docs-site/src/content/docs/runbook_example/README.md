---
title: "Example: Full Runbook Run"
---

# Example: Full Runbook Run

End-to-end walkthrough of Junior reviewing a test repository with intentional bugs.
Each step shows the exact data flowing through the runbook — useful for understanding
what Junior collects, what the LLM receives, and what the output looks like.

The walkthrough uses three example prompts (`security.md`, `logic.md`, `design.md`).
They are merged into a single system prompt and the review runs as one structured
LLM call (see steps 3 and 4).

You can reproduce this by running:

```bash
cd /path/to/test-repo
OPENAI_API_KEY=sk-... junior run --runbook local_review --harness pydantic \
  --prompt-file ./prompts/security.md \
  --prompt-file ./prompts/logic.md \
  --prompt-file ./prompts/design.md \
  --source branch -v
```

## Steps

| Step | File | Description |
|------|------|-------------|
| 0 | [00_test_repo.md](00_test_repo.md) | Test repository setup and intentional bugs |
| 1 | [01_collect.md](01_collect.md) | Phase 1: Collect — git diff, changed files, metadata |
| 2 | [02_context_build.md](02_context_build.md) | Context builder: the user message sent to AI |
| 3 | [03_prompts.md](03_prompts.md) | System prompts: how the prompts are merged into one system prompt |
| 4 | [04_review.md](04_review.md) | Phase 2: AI review — the structured ReviewResult returned by the LLM |
| 5 | [05_publish.md](05_publish.md) | Phase 3: Formatted markdown output |

## Configuration Used

| Setting | Value |
|---------|-------|
| Collector | `local` (no platform API) |
| Harness | `pydantic` (single structured call) |
| Publisher | `local` (stdout) |
| Provider | `openai` |
| Model | `gpt-5.4-mini` |
| Prompts | `security.md`, `logic.md`, `design.md` (merged into one system prompt) |
