# Agent Backends

Configured via `--backend` flag or `AGENT_BACKEND` env var. Default: `claudecode`.

| Backend | Architecture | Auth | Status |
|---------|-------------|------|--------|
| `claudecode` | Single `claude -p` subprocess | Subscription or API key | stable |
| `pydantic` | Parallel sub-agents via pydantic-ai + summary agent | API key required | stable |
| `codex` | Single `codex exec` in sandbox | OAuth or API key | stable |
| `deepagents` | LLM orchestrator + subagents via langchain | API key required | **unstable** |

## How each backend works

| | pydantic | claudecode | codex | deepagents |
|--|----------|-----------|-------|------------|
| **Prompts** | 1 agent per prompt, parallel | All concatenated into system prompt | All concatenated into system prompt | 1 subagent per prompt, orchestrator coordinates |
| **Diff in user message** | Yes | No — reads files via tools | No — reads files via sandbox | Yes |
| **File tools** | `read_file`, `list_dir`, `grep` (Python) | `Read`, `Grep`, `Glob`, `Bash(git...)` (built-in) | Sandbox filesystem access | `read_file`, `ls`, `grep`, `glob` (via deepagents) |
| **Summary** | Separate summary agent call | Single response | Single response | Orchestrator synthesizes |
| **Output** | `SubAgentFindings` → merged → `determine_recommendation()` | `ReviewResult` via `--json-schema` | `ReviewResult` via `--output-schema` | `submit_review` tool captures `ReviewResult` |

## When to use which

| Scenario | Backend | Why |
|----------|---------|-----|
| Local review (default) | `claudecode` | Git tools (log, blame, show), explores beyond diff, no API key needed |
| CI pipeline | `pydantic` | Parallel, structured, predictable cost |
| OpenAI sandbox | `codex` | Isolated exec, file tools |
| Experimental | `deepagents` | Orchestrator pattern — **unstable**, may skip `submit_review` |

Detailed docs:
- [Pydantic AI](agent_backends/pydantic.md)
- [Claude Code](agent_backends/claudecode.md)
- [Codex](agent_backends/codex.md)
- [DeepAgents](agent_backends/deepagents.md)

Adding a new backend: see [Adding backends](adding_backends.md).
