---
title: "Harness: Claude Code CLI"
---

# Harness: Claude Code CLI

**File:** `src/junior/harnesses/claudecode.py`
**Env var:** `HARNESS=claudecode` (default; `BACKEND` is a deprecated alias)
**Dependencies:** `claude` CLI (`npm install -g @anthropic-ai/claude-code`)
**Auth:** Claude Code subscription or `ANTHROPIC_API_KEY` (enables `--bare` API mode)

## Harness Contract

The module exposes a single `HARNESS` instance (`ClaudeCodeHarness`, a `Harness`
subclass). Its one method is schema-agnostic — the result schema is a **parameter**,
not hard-coded:

```python
complete(*, system_prompt: str, user_message: str,
         output_schema: type[BaseModel], settings: Settings) -> LLMResult
```

The code-review runbook passes `LLMReviewOutput` as `output_schema`, but the same
harness drives any runbook's result model. `LLMResult.output` is a validated
instance of `output_schema`; `.usage` carries measured token counts.

`file_access = True` — Claude Code reads repository files via its own tools. The
code-review runbook still inlines the diff while it's small (≤ 50k chars); the tools
serve for context beyond the diff. Only an oversized diff is left to the tools entirely.

> [!NOTE]
> Junior surfaces this harness's progress/status on **stderr** (rich `err_console`)
> while the rendered review goes to **stdout**; structlog logs stay on stderr. See
> `src/junior/cli/console.py`.

## Architecture

```
complete(output_schema=…)
    │
    ▼
schema_json = output_schema.model_json_schema()   ← schema is a parameter
    │
    ▼
subprocess: claude -p   (cwd = settings.context.project_dir)
    │  --output-format json
    │  --json-schema <output_schema JSON schema>
    │  --append-system-prompt <system_prompt>
    │  --tools "Read,Bash(git log/show/diff/blame),Grep,Glob"
    │  --permission-mode bypassPermissions
    │  --no-session-persistence
    │  --bare (when settings.llm.anthropic_api_key is set)
    │  --model <settings.llm.model> (optional)
    │  stdin: user_message
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
_extract_output(messages, output_schema)
    │  finds StructuredOutput tool_use in assistant messages
    │  validates via output_schema.model_validate()
    │
    ▼
LLMResult(output=<output_schema instance>, usage=Usage(input, output, total))
```

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| `--json-schema` from `output_schema.model_json_schema()` | Forces structured output via the StructuredOutput tool — always a dict, no parsing ambiguity, and works for any result schema |
| `file_access = True` | Claude reads files itself via sandbox tools — runbook avoids inlining the full diff |
| `stdin` for `user_message` | Avoids OS argument length limits on large metadata |
| `bypassPermissions` | Required for non-interactive subprocess (no TTY) |
| `--bare` when API key set | `settings.llm.anthropic_api_key` present → API mode; otherwise uses subscription auth |
| Read-only Bash | `Bash(git log:*,git show:*,git diff:*,git blame:*)` — no write operations |
| `settings.llm.model` optional | Claude CLI defaults to its own model; override with `MODEL=claude-sonnet-4-6` etc. |

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

`_extract_output` finds the last `StructuredOutput` tool_use and validates its
`input` dict into the requested `output_schema`. Token usage is extracted from the
`result.usage` object (input + cache-creation + cache-read tokens as input, plus
output tokens) and returned as a `Usage`.

## Error Handling

| Error | Behavior |
|-------|----------|
| CLI not found | RuntimeError with install instructions |
| Timeout (>10 min) | RuntimeError |
| Non-zero exit + no stdout | RuntimeError with stderr |
| Non-zero exit + stdout | Warning logged, output parsed (claude may return partial results) |
| `is_error: true` in result | RuntimeError with error message (e.g., "Not logged in") |
| No StructuredOutput | RuntimeError |
| Validation failure | RuntimeError from `output_schema.model_validate()` |

## vs. Other Harnesses

| Aspect | claudecode | codex | pydantic |
|--------|-----------|-------|----------|
| Driver | `claude -p` subprocess | `codex exec` subprocess | pydantic-ai SDK |
| Provider | Anthropic only | OpenAI only | Any (via pydantic-ai) |
| `file_access` | True (Read/Grep/Glob tools; small diff still inlined) | True (codex sandbox; small diff still inlined) | False (diff always inlined; tools for extra exploration) |
| Structured output | `--json-schema` → StructuredOutput tool | `--output-schema` (strict) file | `output_type=output_schema` |
| Calls | Single subprocess | Single subprocess | Single structured call |
| Model config | `settings.llm.model` (optional) | OpenAI models only | `settings.llm.model_string` (`provider:model`) |
| Auth | OAuth or `ANTHROPIC_API_KEY` | OAuth or `OPENAI_API_KEY` | API key via SDK |
