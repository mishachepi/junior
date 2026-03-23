# Example: Full Pipeline Run

End-to-end run of Junior against a test repository with intentional bugs.

| Step | File | Description |
|------|------|-------------|
| 0 | [00_test_repo.md](00_test_repo.md) | Test repository setup |
| 1 | [01_collect.md](01_collect.md) | Phase 1: Collect context |
| 2 | [02_context_build.md](02_context_build.md) | Context builder: user message for AI |
| 3 | [03_prompts.md](03_prompts.md) | System prompts loaded |
| 4 | [04_review.md](04_review.md) | Phase 2: AI review result |
| 5 | [05_publish.md](05_publish.md) | Phase 3: Formatted output |

## Configuration

- **Collector**: `local`
- **Agent**: `pydantic`
- **Publisher**: `local`
- **Provider**: `openai`
- **Model**: `gpt-5.4-mini`
- **Prompts**: `security,logic,design`
