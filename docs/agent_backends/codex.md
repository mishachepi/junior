# Backend: Codex CLI

**File:** `src/junior/agent/codex.py`
**Env var:** `AGENT_BACKEND=codex`
**Dependencies:** `codex` CLI (`npm install -g @openai/codex`)
**Auth:** `codex login` OAuth or `OPENAI_API_KEY` as fallback

## Architecture

```
review()
    │
    ▼
_ensure_codex_auth()
    │  1. Check `codex login status`
    │  2. If not logged in → `codex login --with-api-key` via OPENAI_API_KEY
    │
    ▼
_build_prompt()
    │  build_review_prompt():  all prompts + BASE_RULES + project instructions
    │  ---
    │  build_user_message(include_diff=False):  MR metadata + file list (no diff)
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

All selected prompts are concatenated into **one text** via `build_review_prompt()` (shared with claudecode). Codex receives a single prompt and decides how to process it. No parallelism — single subprocess call.

Diff is **not** included in the prompt (`include_diff=False`) — codex reads files via its sandbox instead. The user message contains MR metadata and a list of changed files with line counts.

## Output Format

`--output-schema` passes JSON Schema to codex via a temp file. Codex returns structured output matching the schema:

```json
{
  "summary": "...",
  "recommendation": "approve",
  "comments": [...]
}
```

Response parsing handles markdown fences and extracts JSON between first `{` and last `}`.

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
| codex CLI not found | `RuntimeError` with install instructions |
| Not authenticated + no API key | `RuntimeError` with auth instructions |
| Timeout (>10 min) | `RuntimeError` |
| Exit code != 0 | `RuntimeError` with stderr |
| Empty output | `RuntimeError` |
| Invalid JSON | `RuntimeError` |
| Schema validation failure | `RuntimeError` |
