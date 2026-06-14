---
title: "Harness: Codex CLI"
---

# Harness: Codex CLI

**File:** `src/junior/harnesses/codex.py`
**Env var:** `HARNESS=codex` (`BACKEND` is a deprecated alias)
**Dependencies:** `codex` CLI (`npm install -g @openai/codex`) + the `codex` extra (pulls in `openai`)
**Auth:** `codex login` OAuth or `OPENAI_API_KEY` as fallback

## Harness Contract

The module exposes a single `HARNESS` instance (`CodexHarness`, a `Harness`
subclass). Its one method is schema-agnostic — the result schema is a **parameter**:

```python
complete(*, system_prompt: str, user_message: str,
         output_schema: type[BaseModel], settings: Settings) -> LLMResult
```

The code-review runbook passes `LLMReviewOutput`, but the harness works for any
runbook's result model. `LLMResult.output` is a validated instance of
`output_schema`.

`file_access = True` — codex reads repository files via its own sandbox. The
code-review runbook still inlines the diff while it's small (≤ 50k chars); the sandbox
serves for context beyond the diff. Only an oversized diff is left to the sandbox entirely.

## Architecture

```
complete(output_schema=…)
    │
    ▼
_ensure_codex_auth(settings)
    │  1. Check `codex login status`
    │  2. If not logged in → `codex login --with-api-key` via settings.llm.openai_api_key
    │
    ▼
prompt = system_prompt + "\n---\n\n" + user_message
schema  = _build_output_schema(output_schema)   ← strict JSON schema, a parameter
    │
    ▼
subprocess: codex exec
    │  --output-schema schema.json    ← strict schema from output_schema
    │  -o output.txt                   ← response to file
    │  -C settings.context.project_dir ← working directory
    │  --ephemeral                     ← no session persistence
    │  --skip-git-repo-check           ← for Docker/CI
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
_parse_response(raw, output_schema)
    │  1. Strip markdown fences
    │  2. Extract JSON { ... }
    │  3. output_schema.model_validate()
    │
    ▼
LLMResult(output=<output_schema instance>, usage=Usage(total_tokens=N))
```

## Prompt Handling

The `system_prompt` and `user_message` (assembled by the runbook) are concatenated
into **one text** separated by `\n---\n`. Codex receives a single prompt — one
subprocess call, no parallelism.

Because `file_access = True`, the diff is **not** inlined; the user message carries
metadata only and codex reads files via its sandbox.

## Output Format

`--output-schema` passes a **strict** JSON Schema to codex via a temp file. The
schema is built from the requested `output_schema` with
`openai.lib._pydantic.to_strict_json_schema` — this is the only reason the `codex`
extra depends on `openai`. Codex returns structured output matching the schema:

```python
def _build_output_schema(output_schema: type[BaseModel]) -> dict:
    from openai.lib._pydantic import to_strict_json_schema
    return to_strict_json_schema(output_schema)
```

```json
{
  "summary": "...",
  "recommendation": "approve",
  "comments": [...]
}
```

`_parse_response` strips markdown fences, extracts the JSON between the first `{`
and last `}`, then validates into `output_schema`.

## Token Tracking

Codex writes usage to stderr:

```
tokens used
22,476
```

`_parse_token_usage` scans stderr lines for the literal `tokens used` marker, then
validates the next line as a digit/comma sequence (`re.fullmatch(r"\d[\d,]*")`).
Without the marker — or if the value line is malformed — we report `0` and log a
debug/warning, instead of grabbing stray digits from elsewhere in stderr. The count
is returned as `Usage(total_tokens=N)`.

## Error Handling

| Situation | Behavior |
|-----------|----------|
| codex CLI not found | `RuntimeError` with install instructions |
| Not authenticated + no API key | `RuntimeError` with auth instructions |
| Timeout (>10 min) | `RuntimeError` |
| Exit code != 0 | `RuntimeError` with stderr |
| Empty output | `RuntimeError` |
| Invalid JSON | `RuntimeError` |
| Schema validation failure | `RuntimeError` from `output_schema.model_validate()` |
