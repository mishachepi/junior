# Example: Full Pipeline Run

End-to-end walkthrough of Junior reviewing a test repository with intentional bugs.
Each step shows the exact data flowing through the pipeline — useful for understanding
what Junior collects, what the LLM receives, and what the output looks like.

You can reproduce this by running:

```bash
cd /path/to/test-repo
OPENAI_API_KEY=sk-... junior --backend pydantic --prompts security,logic,design --source branch -v
```

## Steps

| Step | File | Description |
|------|------|-------------|
| 0 | [00_test_repo.md](00_test_repo.md) | Test repository setup and intentional bugs |
| 1 | [01_collect.md](01_collect.md) | Phase 1: Collect — git diff, changed files, metadata |
| 2 | [02_context_build.md](02_context_build.md) | Context builder: the user message sent to AI |
| 3 | [03_prompts.md](03_prompts.md) | System prompts: what each agent receives as instructions |
| 4 | [04_review.md](04_review.md) | Phase 2: AI review — raw ReviewResult JSON |
| 5 | [05_publish.md](05_publish.md) | Phase 3: Formatted markdown output |

## Configuration Used

| Setting | Value |
|---------|-------|
| Collector | `local` (no platform API) |
| Agent | `pydantic` (parallel agents via asyncio) |
| Publisher | `local` (stdout) |
| Provider | `openai` |
| Model | `gpt-5.4-mini` |
| Prompts | `security,logic,design` (3 parallel agents) |
