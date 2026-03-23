---
status: in_development
---

# Backend: Codex CLI

**File:** `src/junior/agent/codex.py`
**Env var:** `AGENT_BACKEND=codex`
**Dependencies:** `codex` CLI (`npm install -g @openai/codex`)
**Auth:** `OPENAI_API_KEY`

## Architecture

```
review()
    │
    ▼
_build_prompt()
    │  concatenates all prompts into one text:
    │  ## Analysis: security
    │  {security prompt body}
    │  ## Analysis: logic
    │  {logic prompt body}
    │  ---
    │  ## MR context + diff
    │
    ▼
subprocess: codex exec
    │  --output-schema schema.json    ← JSON Schema for ReviewResult
    │  --ephemeral                     ← no session persistence
    │  --skip-git-repo-check          ← for Docker/CI
    │  -o output.txt                   ← response to file
    │  -C <project_dir>                ← working directory
    │
    │  ┌─────────────────────────────┐
    │  │      codex sandbox          │
    │  │  (read-only by default)     │
    │  │                             │
    │  │  - reads project files      │
    │  │  - runs commands            │
    │  │  - reasoning + tool use     │
    │  │  - structured output        │
    │  └─────────────────────────────┘
    │
    ▼
_parse_response()
    │  1. Strip markdown fences
    │  2. Extract JSON { ... }
    │  3. ReviewResult.model_validate()
    │
    ▼
ReviewResult(tokens_used=N)
```

## Prompt Handling

All selected prompts are concatenated into **one text**. Codex receives a single prompt and decides how to process it. No parallelism — single API call.

```
## Analysis: security
You are a security expert...

## Analysis: logic
You are a logic analysis expert...

## Rules
- Only report issues you are confident about
...
---
## Merge Request: feat: add farewell
**Branches:** feature/add-farewell → main
### Diff
...
```

## Output Format

`--output-schema` passes JSON Schema to codex. Codex guarantees the response matches the schema:

```json
{
  "type": "object",
  "required": ["summary", "recommendation", "comments"],
  "additionalProperties": false,
  "properties": {
    "summary": { "type": "string" },
    "recommendation": { "enum": ["approve", "request_changes", "comment"] },
    "comments": { "type": "array", "items": { ... } }
  }
}
```

**Important:** OpenAI structured output requires `additionalProperties: false` on every object.

## File Access

Codex manages its own file access via sandbox. It reads project files, runs commands, and explores the codebase autonomously. No explicit tools needed — codex has built-in file operations.

## Token Tracking

Codex writes usage to stderr:

```
tokens used
22,476
```

Parsed via regex: `r"(\d[\d,]+)\s*$"` from the last line of stderr.

## Error Handling

| Situation | Behavior |
|-----------|----------|
| codex CLI not found | `RuntimeError: codex CLI not found` |
| Timeout (>5 min) | `RuntimeError: codex CLI timed out` |
| Exit code != 0 | `RuntimeError` with stderr |
| Empty output | `RuntimeError: codex returned empty output` |
| Invalid JSON | `RuntimeError: Failed to parse` |
| Schema mismatch | `RuntimeError: validation failed` |

## Pros and Cons

| Pros | Cons |
|------|------|
| Single subprocess, predictable cost | No prompt parallelism |
| Codex reads files itself (sandbox) | Requires Node.js in Docker |
| `--output-schema` guarantees format | Stderr token parsing (fragile) |
| Uses `OPENAI_API_KEY` directly | Depends on codex CLI version |
| Works in read-only sandbox | Can't control which files it reads |

## Test Results

| Model | Tokens | Findings | Quality |
|-------|--------|----------|---------|
| gpt-5.3-codex | 22,476 | 0 | Clean, approve |
