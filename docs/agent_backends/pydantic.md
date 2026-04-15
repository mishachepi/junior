# Backend: Pydantic AI

**File:** `src/junior/agent/pydantic.py`
**Env var:** `AGENT_BACKEND=pydantic`
**Dependencies:** `pydantic-ai-slim[anthropic,openai]`
**Auth:** `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`

## Architecture

```
review() → asyncio.run(_review_async())
    │
    ▼
_review_async()
    │  1. Build system prompt: prompt body + project instructions (AGENT.md/CLAUDE.md)
    │  2. Create Agent per prompt with file tools
    │  3. asyncio.gather with Semaphore(MAX_CONCURRENT_AGENTS)
    │  4. Merge findings, collect errors from failed agents
    │  5. Summary agent (separate LLM call)
    │  6. determine_recommendation() — programmatic, no LLM
    │
    ▼
          asyncio.gather (parallel, limited by semaphore)
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
        determine_recommendation()  ← programmatic, no LLM
                       │
                       ▼
              ReviewResult(tokens_used=total)
```

## Prompt Handling

Each prompt from `--prompts` becomes a **separate Agent** running in parallel, limited by `MAX_CONCURRENT_AGENTS` (default: 3):

```python
agents = [
    Agent(
        model_str,
        output_type=SubAgentFindings,
        deps_type=ReviewDeps,
        system_prompt=_build_system_prompt(p.body),  # prompt + project instructions
        tools=_TOOLS,
    )
    for p in prompts
]

semaphore = asyncio.Semaphore(settings.max_concurrent_agents)
results = await asyncio.gather(*(_run_with_limit(agent) for agent in agents), return_exceptions=True)
```

- 3 prompts → 3 agents → up to 3 parallel API calls
- 1 prompt → 1 agent → 1 call
- `MAX_TOKENS_PER_AGENT` limits response tokens per agent via `UsageLimits`

## Output Format

Sub-agents return `SubAgentFindings` — pydantic-ai handles structured output natively:

```python
class SubAgentFindings(BaseModel):
    comments: list[ReviewComment] = []
```

Recommendation is determined programmatically after merging all findings:

```python
if any critical OR high_count >= 3:  → REQUEST_CHANGES
if no comments:                      → APPROVE
else:                                → COMMENT
```

## File Tools

Three tools registered on every sub-agent, all restricted to `ci_project_dir`:

| Tool | Limit | Description |
|------|-------|-------------|
| `_read_file(path)` | `MAX_FILE_SIZE` (default 100KB) | Read file content |
| `_list_dir(path)` | — | List directory entries |
| `_grep(pattern, path)` | 50 results max | Regex search in files |

All tools skip directories: `.git`, `node_modules`, `.venv`, `venv`, `__pycache__`, `.tox`, `dist`, `build`. Path traversal outside project root is blocked.

## Token Tracking

pydantic-ai returns exact usage via `result.usage()`. Total includes all sub-agents + summary agent:

```python
for r in results:
    total_tokens += r.usage().total_tokens or 0
total_tokens += summary_result.usage().total_tokens or 0
```

## Error Handling

| Situation | Behavior |
|-----------|----------|
| Sub-agent API call fails | Exception caught via `return_exceptions=True`, added to `review_errors` |
| All sub-agents fail | `RuntimeError` raised |
| Some sub-agents fail | Partial results returned with errors listed in `review_errors` |
| Validation error | pydantic-ai retries automatically |
| No findings | Empty comments, summary agent says "code looks good", recommendation=APPROVE |
| Tool error (file not found) | Error string returned to agent, agent continues review |
