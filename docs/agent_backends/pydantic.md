---
status: in_development
---

# Backend: Pydantic AI

**File:** `src/junior/agent/pydantic.py`
**Env var:** `AGENT_BACKEND=pydantic` (default)
**Dependencies:** `pydantic-ai-slim[anthropic,openai]`
**Auth:** `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`

## Architecture

```
review() → asyncio.run(_review_async())
    │
    ▼
_review_async()
    │  1. Create Agent per prompt
    │  2. asyncio.gather — all in parallel
    │  3. Merge findings
    │  4. Summary agent
    │  5. Programmatic recommendation
    │
    ▼
          asyncio.gather (parallel)
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
   ┌──────────┐  ┌──────────┐  ┌──────────┐
   │ Agent(    │  │ Agent(    │  │ Agent(    │
   │ security) │  │ logic)    │  │ design)   │
   │           │  │           │  │           │
   │ output:   │  │ output:   │  │ output:   │
   │ SubAgent  │  │ SubAgent  │  │ SubAgent  │
   │ Findings  │  │ Findings  │  │ Findings  │
   │           │  │           │  │           │
   │ tools:    │  │ tools:    │  │ tools:    │
   │ read_file │  │ read_file │  │ read_file │
   │ list_dir  │  │ list_dir  │  │ list_dir  │
   │ grep      │  │ grep      │  │ grep      │
   └─────┬─────┘  └─────┬─────┘  └─────┬─────┘
         │              │              │
         └──────────────┼──────────────┘
                        ▼
              merge all comments[]
                        │
                        ▼
              ┌──────────────────┐
              │  summary_agent   │  ← 1 extra API call
              │  output: str     │
              └────────┬─────────┘
                       ▼
        _determine_recommendation()  ← programmatic, no LLM
                       │
                       ▼
              ReviewResult(tokens_used=total)
```

## Prompt Handling

Each prompt from `--prompts` becomes a **separate Agent** running in parallel:

```python
agents = [
    Agent(model_str, output_type=SubAgentFindings, system_prompt=p.body, tools=_TOOLS)
    for p in prompts
]
results = await asyncio.gather(*(agent.run(user_msg, deps=deps) for agent in agents))
```

- 3 prompts → 3 agents → 3 parallel API calls
- 1 prompt → 1 agent → 1 call (like codex, but with structured output)

## Output Format

Pydantic AI uses `output_type=SubAgentFindings` — the model returns data directly as a Pydantic model. No JSON parsing needed:

```python
class SubAgentFindings(BaseModel):
    comments: list[ReviewComment] = []
```

Recommendation is determined programmatically (no LLM):

```python
if any critical OR high_count >= 3:  → REQUEST_CHANGES
if no comments:                      → APPROVE
else:                                → COMMENT
```

## File Access

Three tools, restricted to `project_dir`:

| Tool | Limit | Description |
|------|-------|-------------|
| `_read_file(path)` | 100KB max | Read file content |
| `_list_dir(path)` | — | List directory entries |
| `_grep(pattern, path)` | 50 results max | Regex search in source files |

Code extensions only: `.py`, `.js`, `.ts`, `.jsx`, `.tsx`, `.go`, `.rs`, `.java`, `.rb`, `.php`.

## Token Tracking

pydantic-ai returns exact usage via `result.usage()`:

```python
for r in results:
    total_tokens += r.usage().total_tokens or 0
total_tokens += summary_result.usage().total_tokens or 0
```

## Error Handling

| Situation | Behavior |
|-----------|----------|
| API call fails | pydantic-ai raises exception, caught in cli.py |
| Validation error | pydantic-ai retries automatically |
| No findings | Returns empty comments, recommendation=APPROVE |
| Tool error (file not found) | Returns error string to agent, agent continues |

## Pros and Cons

| Pros | Cons |
|------|------|
| Parallel agents (asyncio.gather) | Requires async (asyncio.run) |
| Cheapest: ~5K tokens (gpt-5.4) | Sub-agents don't see each other |
| Structured output, no JSON parsing | No LLM orchestrator (less flexible) |
| Accurate token tracking via usage() | Programmatic recommendation |
| Works with Anthropic and OpenAI | Depends on pydantic-ai |

## Test Results

| Model | Tokens | Findings | Quality |
|-------|--------|----------|---------|
| gpt-4o-mini | 13,938 | 9 | Noisy, questionable findings |
| gpt-5.4 | **5,297** | 0 | Clean, precise, concise |
