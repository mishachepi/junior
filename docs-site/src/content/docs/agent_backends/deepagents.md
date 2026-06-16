---
title: "Harness: DeepAgents"
---

# Harness: DeepAgents

> [!WARNING]
> **`deepagents` is deprecated.** It's the least reliable harness — it can skip the
> `submit_review` tool entirely, struggles past ~30KB of diff, and has no retry
> logic. Selecting it prints a deprecation warning at startup. Prefer **`pydantic`**
> (one structured call) for the same "API-only, no CLI" use case.

**File:** `src/junior/harnesses/deepagents.py`
**Env var:** `HARNESS=deepagents` (`BACKEND` is a deprecated alias)
**Dependencies:** `deepagents`, `langchain`, `langchain-anthropic`, `langchain-openai`
**Auth:** `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`

## Harness Contract

The module exposes a single `HARNESS` instance (`DeepAgentsHarness`, a `Harness`
subclass). Its one method is schema-agnostic — the result schema is a **parameter**:

```python
complete(*, system_prompt: str, user_message: str,
         output_schema: type[BaseModel], settings: Settings) -> LLMResult
```

The code-review runbook passes `ReviewOutput`, but the harness works for any
runbook's result model. The `output_schema` becomes the `args_schema` of a
`submit_review` tool that the orchestrator calls exactly once.

`file_access = False` — context is inlined into the user message by the runbook;
the `FilesystemBackend` is for *extra* exploration beyond the diff.

## Architecture

A single langchain orchestrator (`create_deep_agent`) with one tool —
`submit_review`. The orchestrator explores via a `FilesystemBackend` and submits its
synthesized result by calling `submit_review` once. There is **no per-prompt
subagent fan-out**.

```
complete(output_schema=…)
    │
    ▼
submit_tool, captured = _make_submit_tool(output_schema)  ← args_schema = output_schema
backend                = FilesystemBackend(root_dir=settings.context.project_dir)
    │
    ▼
agent = create_deep_agent(
    model=settings.llm.model_string,
    tools=[submit_tool],
    system_prompt=system_prompt + _SUBMIT_INSTRUCTIONS,
    backend=backend,
)
agent.invoke({messages: [HumanMessage(user_message)]},
             config={callbacks: [_TokenCounter()]})
    │
    ▼
┌──────────────────────────────────────────────────────┐
│                  Orchestrator LLM                     │
│                                                      │
│  Step 1: Read the inlined context + explore repo     │
│          (read_file, ls, grep, glob via backend)     │
│                                                      │
│  Step 2: Synthesize, dedup, prioritize               │
│                                                      │
│  Step 3: submit_review(**fields)  ← exactly once      │
│              │                                        │
│              ▼                                        │
│        output_schema(**fields) → captured[0]          │
└──────────────────────────────────────────────────────┘
    │
    ▼
LLMResult(output=captured[0],
          usage=Usage(input, output, total))   ← from _TokenCounter
```

## Prompt Handling

The runbook assembles `system_prompt` and `user_message` (context inlined, since
`file_access = False`). The harness appends `_SUBMIT_INSTRUCTIONS` to the system
prompt — telling the orchestrator to explore and then call `submit_review` exactly
once — and passes the user message as a single `HumanMessage`. One orchestrator, one
submit call.

## Output Format

A LangChain `StructuredTool` whose `args_schema` **is** the requested `output_schema`:

```python
def _make_submit_tool(output_schema: type[BaseModel]):
    captured: list[BaseModel] = []

    def submit_review(**kwargs) -> str:
        obj = output_schema(**kwargs)
        captured.append(obj)
        return "Result submitted."

    tool = StructuredTool.from_function(
        func=submit_review,
        name="submit_review",
        args_schema=output_schema,
        handle_validation_error=True,
    )
    return tool, captured
```

- The LLM sees the full schema with its constraints (for code review: severity,
  category, recommendation enums)
- `handle_validation_error=True` — validation errors are returned as a ToolMessage and
  the LLM retries
- If `submit_review` is never called: `RuntimeError` — the review fails

## File access

Provided by `FilesystemBackend(root_dir=settings.context.project_dir)`:

| Tool | Description |
|------|-------------|
| `read_file(path)` | Read file content |
| `ls(path)` | List directory |
| `grep(pattern, path)` | Regex search |
| `glob(pattern)` | File pattern matching |

The orchestrator decides autonomously which files to read — it can explore beyond the
inlined context.

## Token Tracking

Via a LangChain `BaseCallbackHandler` (`_TokenCounter`) wired in as a callback on
`agent.invoke()`. It sums input/output tokens across every LLM call and the harness
returns them as a `Usage`:

```python
class _TokenCounter(BaseCallbackHandler):
    input_tokens: int = 0
    output_tokens: int = 0

    def on_llm_end(self, response: LangchainLLMResult, **kwargs):
        # Prefer message.usage_metadata (newer langchain)
        # Fallback to generation_info.token_usage (older langchain)
```

## Error Handling

| Situation | Behavior |
|-----------|----------|
| submit_review not called | `RuntimeError` — no result produced (tokens wasted) |
| Multiple submit_review calls | Uses first captured result, logs warning |
| LLM API error | Exception propagates to the runner |
| Infinite tool loop | No built-in limit (risk) |
| Token budget exceeded | No limit (risk) |

## Pros and Cons

| Pros | Cons |
|------|------|
| LLM orchestrator — flexible workflow | Highest token usage of the harnesses |
| File exploration — reads only what's needed | No max_iterations (could loop) |
| `submit_review` args_schema = output_schema | 4 heavy dependencies |
| Can adapt strategy per run | Unpredictable execution time |
| submit_review with validation retry | Least predictable cost |

> [!WARNING]
> DeepAgents is the least reliable harness. The orchestrator sometimes skips
> `submit_review`, especially with sparse prompts or large diffs. Use `pydantic` for
> production.
