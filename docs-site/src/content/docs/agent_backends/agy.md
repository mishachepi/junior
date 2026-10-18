---
title: "Harness: Antigravity CLI (agy)"
---

# Harness: Antigravity CLI (agy)

**File:** `src/junior/harnesses/agy.py`
**Env var:** `HARNESS=agy`
**Dependencies:** `agy` CLI (`brew install --cask antigravity-cli`, or the installer at
[antigravity.google/docs/cli](https://antigravity.google/docs/cli)) — no Python extra (core install)
**Auth:** the CLI's own login — run `agy` once interactively; headless runs reuse the cached credentials (no env var)

## Why agy

[Antigravity CLI](https://antigravity.google/docs/cli) is Google's agentic coding CLI
(the successor to Gemini CLI, which Google shut down in June 2026). It serves Gemini
models and, through Antigravity, Claude and GPT-OSS models too — `agy models` lists them.
This harness drives it for a **single headless call**: the agent may read the repository
with its built-in tools, then the CLI enforces the requested output schema itself and
returns the validated object. Same runbooks as every other harness:

```bash
junior run --harness agy                            # CLI picks its configured model
junior run --harness agy --model gemini-3.1-pro-high
```

Without `--model` the CLI uses the model from its own settings; pass an id from
`agy models` to pin one.

## Harness Contract

The module exposes a single `HARNESS` instance (`AgyHarness`, a `CliHarness` subclass)
with the standard schema-agnostic method:

```python
complete(*, system_prompt: str, user_message: str,
         output_schema: type[BaseModel], llm: LLMSettings, project_dir: Path) -> LLMResult
```

`file_access = False` — the diff is always inlined (capped by `context.max_diff_chars`,
200k by default), because the runbook's "diff dropped, read it with your tools" path needs
`git`, a shell command headless agy denies. agy still reads repository files with its
built-in tools for context beyond the diff — the same shape as `pydantic`.

## Architecture

```
complete(output_schema=…)
    │
    ▼
prompt = system_prompt + headless note + "---" + user_message
    │                                                  ← one argument (agy has no
    │                                                  system-prompt flag, reads no stdin)
    ▼
subprocess: agy --print=<prompt>
    │  --output-format json
    │  --json-schema <output_schema JSON Schema>   ← native structured output
    │  [--model <id>]
    │  cwd = project_dir
    ▼
stdout = JSON envelope { status, response, error?, usage, structured_output?, denied_actions? }
    │
    ▼
_parse_envelope()   status != SUCCESS / error → RuntimeError
    ▼
_extract_output()   structured_output → model_validate()
    │               (fallback: parse the text `response` like pi does)
    ▼
LLMResult(output=<output_schema instance>, usage=Usage(input, output, total))
```

## Prompt Handling

`system_prompt`, a one-line headless note («no shell here — don't run commands, read files
with your file tools») and the runbook's `user_message` are concatenated into one prompt
passed as `--print=<prompt>` (the `=` form keeps a prompt starting with `-` from being parsed as
a flag). agy does not read a prompt from stdin, so the prompt lives in argv: the OS
bounds it (`ARG_MAX` is 1 MiB on macOS, 2 MiB on Linux) — above the runbooks'
`max_diff_chars` cap.

## Output Format

`--json-schema` makes the CLI validate the answer and embed it as `structured_output` in
the envelope; the harness feeds that straight into `output_schema.model_validate()`. If
an agy version omits the field, the text `response` is parsed defensively instead (fences
stripped, outermost `{...}` extracted) and validated the same way. A reply that doesn't
validate fails the run — exactly like every other harness.

## Permissions & read-only

Permissions are agy's, from `~/.gemini/antigravity-cli/settings.json` — Junior passes no
permission flags and never `--dangerously-skip-permissions`. In headless mode the CLI
can't prompt, so anything not allowed is **auto-denied**: the turn still exits `0` with
`status: SUCCESS`, an empty `response` and a `denied_actions` list. The harness turns
that into a `RuntimeError` naming the denied action (e.g. `RunCommand`, `WriteToFile`)
instead of reporting an empty answer.

Verified with agy 1.2.12 on macOS: file **reads** work headlessly; **shell commands and
file writes are denied** unless allowed under `permissions.allow` — also inside a
directory listed in the settings' `trustedWorkspaces`. A review runbook never asks for
either, so the default settings are the right ones for Junior; a runbook that needs the
agent to run or write something gets it through an allow-rule, never through Junior.

## Token Tracking

The envelope's `usage` block carries `input_tokens`, `output_tokens` (inclusive of
`thinking_tokens`), `cache_read_tokens` and `total_tokens`; the harness maps input,
output and total straight onto `Usage`. A missing or differently-shaped block yields
zeros rather than an error.

## Error Handling

| Situation | Behavior |
|-----------|----------|
| agy CLI not found | `RuntimeError` with install instructions |
| Timeout (default 10 min) | `RuntimeError` (raise `llm.timeout` if expected) |
| Empty stdout | `RuntimeError` with the exit code + stderr tail |
| `status` ≠ `SUCCESS` / envelope `error` | `RuntimeError` with the error message |
| Empty response with `denied_actions` | `RuntimeError` naming the denied action |
| Reply is not JSON (fallback path) | `RuntimeError` (logged with the raw reply) |
| Schema validation failure | `RuntimeError` from `output_schema.model_validate()` |
