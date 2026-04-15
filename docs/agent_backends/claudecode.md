# Backend: Claude Code CLI

**File:** `src/junior/agent/claudecode.py`
**Env var:** `AGENT_BACKEND=claudecode` (default)
**Dependencies:** `claude` CLI (`npm install -g @anthropic-ai/claude-code`)
**Auth:** Claude Code subscription or `ANTHROPIC_API_KEY` (enables `--bare` API mode)

## Architecture

```
review()
    │
    ▼
build_review_prompt()          ← shared with codex (core/instructions.py)
    │  ## Analysis: security
    │  {security prompt body}
    │  ## Rules
    │  ...
    │  ## Project-Specific Instructions (AGENT.md/CLAUDE.md)
    │
    ▼
build_user_message(include_diff=False)   ← shared (core/context_builder.py)
    │  MR metadata + changed file list (no full diff)
    │
    ▼
subprocess: claude -p
    │  --output-format json
    │  --json-schema <ReviewResult schema>
    │  --append-system-prompt <system prompt>
    │  --tools "Read,Bash(git log/show/diff/blame),Grep,Glob"
    │  --permission-mode bypassPermissions
    │  --no-session-persistence
    │  --bare (CI only, when ANTHROPIC_API_KEY is set)
    │  --model <MODEL_NAME> (optional)
    │  stdin: user prompt
    │
    │  ┌─────────────────────────────┐
    │  │   Claude Code sandbox       │
    │  │                             │
    │  │  - Read: project files      │
    │  │  - Grep/Glob: search        │
    │  │  - Bash: git log/show/diff  │
    │  │  - StructuredOutput: result │
    │  └─────────────────────────────┘
    │
    ▼
_extract_review()
    │  finds StructuredOutput tool_use in assistant messages
    │  validates via ReviewResult.model_validate()
    │
    ▼
ReviewResult
```

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| `--json-schema` | Forces structured output via StructuredOutput tool — always dict, no parsing ambiguity |
| `include_diff=False` | Claude reads files itself via sandbox tools — avoids sending full diff in prompt |
| `stdin` for prompt | Avoids OS argument length limits on large MR metadata |
| `bypassPermissions` | Required for non-interactive subprocess (no TTY) |
| `--bare` when API key set | `ANTHROPIC_API_KEY` present → API mode; otherwise uses subscription auth |
| Read-only Bash | `Bash(git log:*,git show:*,git diff:*,git blame:*)` — no write operations |
| `MODEL_NAME` optional | Claude CLI defaults to its own model; override with `MODEL_NAME=claude-sonnet-4-6` etc. |

## Output Parsing

Claude `--output-format json` returns a JSON array of message objects:

```json
[
  {"type": "system", "model": "claude-sonnet-4-6", ...},
  {"type": "assistant", "message": {"content": [
    {"type": "tool_use", "name": "Read", ...},
    {"type": "tool_use", "name": "StructuredOutput", "input": {
      "summary": "...",
      "recommendation": "approve",
      "comments": [...]
    }}
  ]}},
  {"type": "result", "is_error": false, "usage": {"input_tokens": ..., "output_tokens": ...}}
]
```

Token usage is extracted from the `result.usage` object (input + output + cache tokens).

## Error Handling

| Error | Behavior |
|-------|----------|
| CLI not found | RuntimeError with install instructions |
| Timeout (>10 min) | RuntimeError |
| Non-zero exit + no stdout | RuntimeError with stderr |
| Non-zero exit + stdout | Warning logged, output parsed (claude may return partial results) |
| `is_error: true` in result | RuntimeError with error message (e.g., "Not logged in") |
| No StructuredOutput | RuntimeError |
| Validation failure | RuntimeError |

## vs. Other Backends

| Aspect | claudecode | codex | pydantic |
|--------|-----------|-------|----------|
| Subprocess | `claude -p` | `codex exec` | Python SDK |
| Provider | Anthropic only | OpenAI only | Any (via pydantic-ai) |
| File access | Read/Grep/Glob tools | Codex sandbox | Custom tools |
| Structured output | `--json-schema` → StructuredOutput tool | `--output-schema` file | Pydantic output type |
| Parallelism | Single call | Single call | asyncio.gather |
| Model config | `MODEL_NAME` (optional) | OpenAI models only | `MODEL_PROVIDER:MODEL_NAME` |
| Auth | OAuth or `ANTHROPIC_API_KEY` | OAuth or `OPENAI_API_KEY` | API key via SDK |
