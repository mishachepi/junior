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
    │  --permission-mode <settings.llm.claudecode.permission_mode>  (default bypassPermissions)
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

## Prompt Handling

`system_prompt` is passed via `--append-system-prompt`; the runbook's `user_message`
goes in on **stdin** (avoids OS argument-length limits on large metadata). It's a single
subprocess call — no parallelism. `settings.llm.model` is optional (the Claude CLI uses
its own default unless `--model` is set, e.g. `MODEL=claude-sonnet-4-6`); with
`settings.llm.anthropic_api_key` set the harness adds `--bare` for API mode.

## Output Format

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
`input` dict into the requested `output_schema`. Newer CLI versions also embed
the validated object directly on the result message as `structured_output`; when
no tool_use is present, the harness falls back to that field — so both output
shapes parse. If neither is found (claude ended on plain text — rate limit,
refusal, out of turns), it raises with the cause and the last text.

## File access

`file_access = True` — Claude reads the repository itself, so the runbook needn't inline
an oversized diff. The tools are read-only: `Read`, `Grep`, `Glob`, and
`Bash(git log:*,git show:*,git diff:*,git blame:*)` — no write operations.

## Permission mode

`--permission-mode` is set from `llm.claudecode.permission_mode` (YAML only — nested
under the `llm` group):

```yaml
llm:
  harness: claudecode
  claudecode:
    permission_mode: acceptEdits   # default | acceptEdits | plan | bypassPermissions
```

The default is **`bypassPermissions`**: the subprocess has no TTY, so the built-in
tools can't surface an interactive approval prompt — bypassing lets the read-only
tools above run unattended (junior is usually run in CI / a container, where that's
acceptable). `bypassPermissions` is **unsafe on untrusted content outside a sandbox**
— a malicious diff could try to steer the agent. When you run junior on untrusted
input outside a container, tighten it (e.g. `plan` or `acceptEdits`). Any value the
`claude` CLI rejects fails fast in config validation.

## Token Tracking

Token usage is read from the result message's `usage` object (input + cache-creation +
cache-read tokens counted as input, plus output tokens) and returned as a `Usage`.

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

> [!TIP]
> How claudecode compares to the other harnesses (driver, provider, structured-output
> mechanism, auth) is in the [harness comparison](../agent_backends.md#comparison).
