---
title: "Step 3: System Prompts"
---

# Step 3: System Prompts

**Module**: `junior.runbooks.code_review.instructions.build_review_prompt()` (resolves entries via `junior.prompt_loader.load_prompts()`)

Junior assembles the system instructions from whatever the user supplied via `--prompt`, `--prompt-file`, or the config file. This walkthrough uses the three example files in `examples/prompts/`.

## Loaded Prompts

| Name | Size | Focus |
|------|------|-------|
| `security` | 1,274 chars | Auth bypass, privilege escalation, TOCTOU, path traversal, hardcoded secrets, weak crypto |
| `logic` | 1,619 chars | Incorrect conditions, missing edge cases, error handling, thread safety, resource leaks |
| `design` | 1,423 chars | Naming, DRY/KISS/SRP violations, optimization, config issues, portability |

**Total**: 4,316 chars of system instructions.

## How Prompts Are Used

All three prompts are concatenated into a **single** system prompt. The runbook's
`SYSTEM_PROMPT` role plus the user's `context.prompts` (`--prompt` / `--prompt-file`)
are merged into the system prompt, and the pydantic harness makes one structured LLM call:

```
[merged system prompt] + [user message] --> single structured LLM call --> ReviewResult (summary + recommendation + comments)
```

The single call receives:
- **System prompt**: all prompt bodies (each under a `## Analysis: <name>` header) + BASE_RULES + project instructions (first of `AGENT.md` / `AGENTS.md` / `CLAUDE.md` if present), merged into one string
- **User message**: the context from Step 2
- **Output type**: `LLMReviewOutput` (structured output via pydantic-ai) — the model returns the full result directly
