# Agent Backends

Configured via `AGENT_BACKEND` env var. Default: `pydantic`.

| Backend | Architecture | Tokens (hello world MR) |
|---------|--------------|--------------------------|
| `pydantic` | Parallel agents via asyncio.gather | ~5K |
| `claudecode` | Single subprocess to `claude` CLI | ~120-240K |
| `codex` | Single subprocess with JSON schema | ~22K |
| `deepagents` | LLM orchestrator + subagents | ~88K |

Detailed docs:
- [pydantic.md](agent_backends/pydantic.md)
- [claudecode.md](agent_backends/claudecode.md)
- [codex.md](agent_backends/codex.md)
- [deepagents.md](agent_backends/deepagents.md)

## Comparison (hello world MR, 2 files, 461 chars diff)

| Backend | Model | Prompts | Findings | Tokens | Recommendation |
|---------|-------|---------|----------|--------|----------------|
| pydantic | gpt-5.4 | sec+logic+design (3) | 0 | **5,297** | approve |
| pydantic | gpt-4o-mini | sec+logic+design (3) | 9 | 13,938 | comment |
| codex | gpt-5.3-codex | common (1) | 0 | 22,476 | approve |
| deepagents | gpt-5.4 | sec+logic+design (3) | 0–1 | 88,528 | approve/comment |

## When to use which

| Scenario | Backend | Prompts | Why |
|----------|---------|---------|-----|
| CI pipeline (fast, cheap) | pydantic | common | parallel, low tokens |
| CI pipeline (deeper) | pydantic | security,logic,design | parallel, cheap |
| Claude Code (thorough) | claudecode | security,logic | file tools + git, structured output |
| Large MR (50+ files) | deepagents | security,logic,design | explores repo |
| Codex sandbox | codex | common | 1 subprocess call |

Adding a new agent backend: see [adding_backends.md](adding_backends.md).
