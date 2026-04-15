# Step 3: System Prompts

**Module**: `junior.prompt_loader.load_prompts()`

Loads prompt templates from `src/junior/prompts/*.md` and combines them into system instructions.

## Loaded Prompts

| Name | Size | Focus |
|------|------|-------|
| `security` | 1,274 chars | Auth bypass, privilege escalation, TOCTOU, path traversal, hardcoded secrets, weak crypto |
| `logic` | 1,619 chars | Incorrect conditions, missing edge cases, error handling, thread safety, resource leaks |
| `design` | 1,423 chars | Naming, DRY/KISS/SRP violations, optimization, config issues, portability |

**Total**: 4,316 chars of system instructions.

## How Prompts Are Used

The pydantic backend runs 3 parallel AI agents, one per prompt:

```
                    +---> [security agent] --+
User Message ------>+---> [logic agent]    --+--> merge results --> ReviewResult
                    +---> [design agent]   --+
```

Each agent receives:
- **System message**: the prompt body + BASE_RULES + project instructions (AGENT.md/CLAUDE.md if present)
- **User message**: the context from Step 2
- **Output type**: `SubAgentFindings` (structured output via pydantic-ai)
