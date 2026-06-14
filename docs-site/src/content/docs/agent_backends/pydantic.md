---
title: "Harness: Pydantic AI"
---

# Harness: Pydantic AI

**File:** `src/junior/harnesses/pydantic.py`
**Env var:** `HARNESS=pydantic` (`BACKEND` is a deprecated alias)
**Dependencies:** `pydantic-ai-slim[anthropic,openai]`
**Auth:** `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`

## Harness Contract

The module exposes a single `HARNESS` instance (`PydanticHarness`, a `Harness`
subclass). Its one method is schema-agnostic — the result schema is a **parameter**:

```python
complete(*, system_prompt: str, user_message: str,
         output_schema: type[BaseModel], settings: Settings) -> LLMResult
```

The code-review runbook passes `LLMReviewOutput`, but the harness works for any
runbook's result model. The model returns an instance of `output_schema` directly.

`file_access = False` — the diff is **inlined** into the user message by the
runbook; the harness's file tools exist only for *extra* exploration beyond the diff.

## Architecture

A **single structured call** via the pydantic-ai SDK. One `Agent`, one `run()` —
the model returns an `output_schema` instance directly. There is no per-prompt
fan-out and no separate summary agent.

```
complete(output_schema=…) → asyncio.run(_run(...))
    │
    ▼
model_str = settings.llm.model_string
deps      = ReviewDeps(project_dir, max_file_size=settings.llm.max_file_size)
limits    = UsageLimits(response_tokens_limit=settings.llm.max_tokens_per_agent)
    │
    ▼
┌──────────────────────────────────────────────┐
│  Agent(                                       │
│    model_str,                                 │
│    output_type=output_schema,   ← a parameter │
│    deps_type=ReviewDeps,                      │
│    system_prompt=system_prompt,               │
│    tools=[_read_file, _list_dir, _grep],      │
│  )                                            │
│                                               │
│  result = await agent.run(user_message,       │
│                           deps=deps,          │
│                           usage_limits=limits)│
│                                               │
│  - model may call read_file / list_dir / grep │
│    to explore beyond the inlined diff         │
│  - returns a validated output_schema instance │
└──────────────────────┬───────────────────────┘
                       ▼
LLMResult(output=result.output,
          usage=Usage(input, output, total))   ← from result.usage()
```

## Prompt Handling

The runbook assembles `system_prompt` and `user_message` (the latter with the diff
inlined, since `file_access = False`). The harness makes a single `agent.run()` call.
`settings.llm.max_tokens_per_agent`, when set, caps the response via `UsageLimits`.

## Output Format

pydantic-ai handles structured output natively via `output_type`. The agent is
constructed with `output_type=output_schema`, and `result.output` is a validated
instance of that schema — for code review, an `LLMReviewOutput` (summary,
recommendation, comments). No post-hoc parsing or programmatic recommendation step
lives in the harness; the model fills the schema directly.

## File Tools

Three tools are registered on the agent, all restricted to
`settings.context.project_dir`. Because the diff is already inlined, these are for
*optional* deeper exploration:

| Tool | Limit | Description |
|------|-------|-------------|
| `_read_file(path)` | `settings.llm.max_file_size` (default 100KB) | Read file content |
| `_list_dir(path)` | — | List directory entries |
| `_grep(pattern, path)` | 50 results max | Regex search in files |

All tools skip directories: `.git`, `node_modules`, `.venv`, `venv`, `__pycache__`,
`.tox`, `dist`, `build`. Path traversal outside the project root is blocked
(`_safe_resolve`).

## Token Tracking

pydantic-ai returns exact usage via `result.usage()`. The harness reads
`input_tokens` and `output_tokens` from that single call and returns them as a
`Usage` (with `total = input + output`):

```python
u = result.usage()
input_t = u.input_tokens or 0
output_t = u.output_tokens or 0
return LLMResult(
    output=result.output,
    usage=Usage(input_tokens=input_t, output_tokens=output_t,
                total_tokens=input_t + output_t),
)
```

## Error Handling

| Situation | Behavior |
|-----------|----------|
| API call fails | Exception propagates from `agent.run()` |
| Validation error | pydantic-ai retries automatically |
| No findings | Model returns an empty `comments` list in the `output_schema` instance |
| Tool error (file not found) | Error string returned to the agent, which continues |
