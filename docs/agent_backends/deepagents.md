---
status: unstable,bugs
---

# Backend: DeepAgents

**File:** `src/junior/agent/deepagents.py`
**Env var:** `AGENT_BACKEND=deepagents`
**Dependencies:** `deepagents`, `langchain`, `langchain-anthropic`, `langchain-openai`
**Auth:** `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`

## Architecture

```
review()
    │
    ▼
create_deep_agent()
    │  model = "openai:gpt-5.4"
    │  system_prompt = _build_orchestrator_prompt() (dynamic)
    │  tools = [submit_review]
    │  subagents = [{name, description, system_prompt}]
    │  backend = FilesystemBackend(root_dir=project_dir)
    │
    ▼
agent.invoke() with TokenCounter callback
    │
    ▼
┌──────────────────────────────────────────────────────┐
│                  Orchestrator LLM                     │
│                                                      │
│  Step 1: Read diff, understand context               │
│          (read_file, grep, ls, glob)                 │
│                                                      │
│  Step 2: Delegate to subagents via task()            │
│          task("security", msg)                       │
│          task("logic", msg)                          │
│          task("design", msg)                         │
│              │         │         │                    │
│              ▼         ▼         ▼                    │
│         ┌────────┐┌────────┐┌────────┐               │
│         │security││ logic  ││ design │               │
│         │        ││        ││        │               │
│         │ JSON   ││ JSON   ││ JSON   │               │
│         │ array  ││ array  ││ array  │               │
│         └───┬────┘└───┬────┘└───┬────┘               │
│             └─────────┼─────────┘                     │
│                       │                              │
│  Step 3: Synthesize, dedup, prioritize               │
│                       │                              │
│  Step 4: submit_review(summary=..., comments=[...])  │
│                       │                              │
│                       ▼                              │
│            captured[0] → ReviewResult                 │
└──────────────────────────────────────────────────────┘
    │
    ▼
TokenCounter.total_tokens → result.tokens_used
```

## Prompt Handling

Each prompt becomes a subagent dict. Orchestrator prompt is built dynamically with subagent names:

```python
subagents = [
    {
        "name": p.name,               # "security"
        "description": p.description,  # "Security vulnerability analysis"
        "system_prompt": p.body + _SUBAGENT_OUTPUT_INSTRUCTIONS,
        "tools": [],
    }
    for p in prompts
]
```

Subagents return JSON arrays (not structured output). The orchestrator synthesizes results and calls `submit_review`.

## Output Format

LangChain `StructuredTool` with `args_schema=ReviewResult`:

```python
def submit_review(**kwargs) -> str:
    result = ReviewResult(**kwargs)
    captured.append(result)
    return f"Review submitted: {result.recommendation.value}, {len(result.comments)} comments."
```

- LLM sees schema with enum constraints (severity, category, recommendation)
- `handle_validation_error=True` — validation errors returned as ToolMessage, LLM retries
- Fallback if `submit_review` not called: `ReviewResult(summary="submit_review was not called")`

## File Access

Provided by `FilesystemBackend(root_dir=project_dir)`:

| Tool | Description |
|------|-------------|
| `read_file(path)` | Read file content |
| `ls(path)` | List directory |
| `grep(pattern, path)` | Regex search |
| `glob(pattern)` | File pattern matching |
| `task(agent_name, msg)` | Delegate to subagent |

The orchestrator decides autonomously which files to read — it can explore beyond the diff.

## Token Tracking

Via LangChain `BaseCallbackHandler`:

```python
class _TokenCounter(BaseCallbackHandler):
    total_tokens: int = 0

    def on_llm_end(self, response: LLMResult, **kwargs):
        # Extract from generation_info.token_usage (older langchain)
        # Fallback to message.usage_metadata (newer langchain)
```

### Why ~88K Tokens

```
Orchestrator reasoning + planning     ~15K
Orchestrator file exploration          ~20K
3x subagent system_prompt + context   ~30K
3x subagent response                   ~5K
Orchestrator synthesis + submit        ~18K
─────────────────────────────────────
Total                                  ~88K
```

## Error Handling

| Situation | Behavior |
|-----------|----------|
| submit_review not called | Fallback: `ReviewResult(summary="submit_review was not called")` |
| Multiple submit_review calls | Uses first result, logs warning |
| LLM API error | Exception propagates to cli.py |
| Infinite tool loop | No built-in limit (risk, TODO: add max_iterations) |
| Token budget exceeded | No limit (risk, TODO: add max_iterations) |

## Pros and Cons

| Pros | Cons |
|------|------|
| LLM orchestrator — flexible workflow | ~88K tokens (17x more than pydantic) |
| File exploration — reads only what's needed | No max_iterations (could loop) |
| Subagent orchestration | 4 heavy dependencies |
| Can adapt review strategy per MR | Unpredictable execution time |
| submit_review with validation retry | Subagents return JSON (fragile) |

## Test Results

| Model | Tokens | Findings | Quality |
|-------|--------|----------|---------|
| gpt-5.4 (run 1) | 88,528 | 1 (medium) | Accurate: pytest in main deps |
| gpt-5.4 (run 2) | 88,528 | 0 | Clean, approve |

Instability: same model and prompt give different results. Normal for LLM-orchestrated workflows.
