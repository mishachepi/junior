---
title: "Harness: Pydantic AI"
---

# Harness: Pydantic AI

**File:** `src/junior/harnesses/pydantic.py`
**Env var:** `HARNESS=pydantic` (default)
**Dependencies:** `pydantic-ai-slim[anthropic,openai]`
**Auth:** `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` — or a local OpenAI-compatible server via `OPENAI_BASE_URL` (see [Local models](#local-models-openai-compatible-servers))

## Harness Contract

The module exposes a single `HARNESS` instance (`PydanticHarness`, a `Harness`
subclass). Its one method is schema-agnostic — the result schema is a **parameter**:

```python
complete(*, system_prompt: str, user_message: str,
         output_schema: type[BaseModel], llm: LLMSettings, project_dir: Path) -> LLMResult
```

The code-review runbook passes `ReviewOutput`, but the harness works for any
runbook's result model. The model returns an instance of `output_schema` directly.

`file_access = False` — the diff is **inlined** into the user message by the
runbook; the harness's file tools exist only for *extra* exploration beyond the diff.

## Local models (OpenAI-compatible servers)

Nothing in Junior is cloud-specific: the `openai:` provider is pydantic-ai's
OpenAI client, and that client honours the standard `OPENAI_BASE_URL` variable.
Point it at any OpenAI-compatible server — oMLX, Ollama, LM Studio, vLLM,
llama.cpp — and name the model with the `openai:` prefix:

```bash
export OPENAI_BASE_URL=http://127.0.0.1:9009/v1        # oMLX (Ollama: :11434/v1, LM Studio: :1234/v1)
export OPENAI_API_KEY=sk-local                          # the server's key; any non-empty value if it has none
junior run --harness pydantic --model openai:gemma-4-12B-it-qat-OptiQ-4bit
```

`OPENAI_API_KEY` must be set even for a server without auth: Junior's preflight
requires a key for the `openai` provider, and the SDK sends it as a bearer token
the server ignores. Everything else is unchanged — the same structured call, the
same file tools, `usage` from the server's token counts. The structured output is
a pydantic-ai *tool call*, so the model and server must support OpenAI tool
calling — and the model must fill the schema faithfully: a small model can
answer the tool call with its own field names (seen with gemma-4-12B on
`ReviewOutput`: `comment`/`file` instead of `message`/`file_path`), which fails
the run after pydantic-ai's one retry. A one-field schema works fine on the same
model. For such models the `pi` harness puts the schema in the prompt instead —
see [Harness: pi](pi.md).

## Architecture

A **single structured call** via the pydantic-ai SDK. One `Agent`, one `run()` —
the model returns an `output_schema` instance directly. There is no per-prompt
fan-out and no separate summary agent.

```
complete(output_schema=…) → asyncio.run(_run(...))
    │
    ▼
model_str = llm.model_string
deps      = ReviewDeps(project_dir, max_file_size=llm.max_file_size)
limits    = UsageLimits(output_tokens_limit=llm.max_tokens_per_agent)
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
`llm.max_tokens_per_agent`, when set, caps the response via `UsageLimits`.

## Output Format

pydantic-ai handles structured output natively via `output_type`. The agent is
constructed with `output_type=output_schema`, and `result.output` is a validated
instance of that schema — for code review, an `ReviewOutput` (summary,
recommendation, comments). No post-hoc parsing or programmatic recommendation step
lives in the harness; the model fills the schema directly.

## File access

Three tools are registered on the agent, all restricted to
`project_dir`. Because the diff is already inlined, these are for
*optional* deeper exploration:

| Tool | Limit | Description |
|------|-------|-------------|
| `_read_file(path)` | `llm.max_file_size` (default 100KB) | Read file content |
| `_list_dir(path)` | — | List directory entries |
| `_grep(pattern, path)` | 50 results max | Regex search in files |

All tools skip directories: `.git`, `node_modules`, `.venv`, `venv`, `__pycache__`,
`.tox`, `dist`, `build`. Path traversal outside the project root is blocked
(`_safe_resolve`).

## Token Tracking

pydantic-ai returns exact usage via `result.usage`. The harness reads
`input_tokens` and `output_tokens` from that single call and returns them as a
`Usage` (with `total = input + output`):

```python
u = result.usage
input_t = u.input_tokens or 0
output_t = u.output_tokens or 0
return LLMResult(
    output=result.output,
    usage=Usage(input_tokens=input_t, output_tokens=output_t,
                total_tokens=input_t + output_t),
)
```

## Error Handling

Provider/SDK failures from `agent.run()` are translated into actionable
`RuntimeError`s (`_translate_error`); anything unrecognized re-raises as-is.

| Situation | Behavior |
|-----------|----------|
| Input exceeds the model's context window (HTTP 400, provider phrasing matched) | `RuntimeError`: "input is too large for model …" + hints (`context.max_diff_chars`, `llm.max_file_size`, bigger model) |
| Rate limit (HTTP 429) | `RuntimeError` with the provider message + retry hint |
| Bad API key (HTTP 401/403) | `RuntimeError` pointing at `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` |
| Other HTTP 4xx/5xx | `RuntimeError` with status + provider message |
| `max_tokens_per_agent` cap hit (`UsageLimitExceeded`) | `RuntimeError` pointing at `llm.max_tokens_per_agent` |
| Validation error | pydantic-ai retries automatically |
| No findings | Model returns an empty `comments` list in the `output_schema` instance |
| Tool error (file not found) | Error string returned to the agent, which continues |
