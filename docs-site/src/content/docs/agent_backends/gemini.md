---
title: "Harness: Gemini CLI"
---

# Harness: Gemini CLI

**File:** `src/junior/harnesses/gemini.py`
**Env var:** `HARNESS=gemini`
**Dependencies:** `gemini` CLI (`npm install -g @google/gemini-cli`) — no Python extra (core install)
**Auth:** `GEMINI_API_KEY`, or the CLI's own logged-in auth / Vertex env — no local key required if already set up

## Why gemini

[Gemini CLI](https://geminicli.com) is Google's agentic coding CLI. This harness drives
it for a **read-only review**: a single non-interactive call that may read the repository
with the CLI's built-in tools, then answers with one JSON object. Use it to run reviews
on Gemini models with the same runbooks as every other harness:

```bash
junior run --harness gemini                       # CLI picks its default model
junior run --harness gemini --model gemini-2.5-pro
```

Without `--model` the CLI uses its own configured default; pass a Gemini model id to pin
one.

## Harness Contract

The module exposes a single `HARNESS` instance (`GeminiHarness`, a `Harness` subclass)
with the standard schema-agnostic method:

```python
complete(*, system_prompt: str, user_message: str,
         output_schema: type[BaseModel], settings: Settings) -> LLMResult
```

`file_access = True` — gemini explores the repository with its built-in tools, but the
harness pins `--approval-mode plan` (**read-only**): the CLI may read files but never
edits or runs anything, so a review can't mutate the worktree. The code-review runbook
still inlines the diff while it's small (≤ 50k chars); the tools serve for context beyond
it.

## Architecture

```
complete(output_schema=…)
    │
    ▼
prompt = system_prompt + "## Output format" + JSON Schema + "---" + user_message
    │     (gemini's CLI has no native structured-output flag — the schema
    │      contract is embedded in the prompt and enforced on our side)
    ▼
subprocess: gemini --output-format json
    │  --approval-mode plan        ← read-only: read the repo, never edit/run
    │  --skip-trust                ← headless: keep plan mode (don't downgrade in an untrusted dir)
    │  [--model <id>]
    │  stdin = <prompt>            ← whole prompt on stdin (no ARG_MAX limit on big diffs)
    │
    ▼
stdout = JSON envelope { response, stats, error? }
    │
    ▼
_parse_envelope(stdout, returncode, stderr)
    │  text  = envelope.response
    │  usage = Σ stats.models[*].tokens (prompt → input, candidates → output)
    ▼
parse_json_reply(text, output_schema, source="gemini")
    │  strip fences → extract outermost {...} → model_validate()
    ▼
LLMResult(output=<output_schema instance>, usage=Usage(...))
```

## Prompt Handling

`system_prompt`, the JSON-Schema output contract, and the runbook's `user_message` are
concatenated into one prompt delivered on **stdin** (so a large inlined diff never hits
the OS argument-size limit). The non-TTY subprocess triggers gemini's headless mode. It's
a single subprocess call — no parallelism. Because `file_access = True`, an oversized diff
is left to gemini's read tools while a small one is inlined by the runbook.

## Output Format

Gemini's CLI has no per-call output-schema flag (its `--output-format json` shapes the
*CLI envelope*, not the model's answer). So the harness appends an output contract to the
prompt («reply with ONLY one JSON object matching this JSON Schema: …»), reads the
envelope's `response` field, then parses defensively: code fences are stripped, the
outermost `{...}` is extracted from any surrounding prose, then
`output_schema.model_validate()` enforces the real contract. A reply that doesn't validate
fails the run — exactly like every other harness.

## File access

`file_access = True`, but **read-only by construction**: `--approval-mode plan` lets the
CLI read the repo with its built-in tools while blocking every edit/shell action, so a
review can never mutate the repository. There is no knob to loosen this in Junior.

## Token Tracking

The JSON envelope's `stats.models` map carries per-model token counts
(`{prompt, candidates, total, cached}`). The harness sums `prompt` as input (Gemini bills
prompt tokens inclusive of cached ones — no double count) and `candidates` as output,
across every model in the run. A missing or differently-shaped stats block yields zeros
rather than an error.

## Error Handling

| Situation | Behavior |
|-----------|----------|
| gemini CLI not found | `RuntimeError` with install instructions |
| Timeout (default 10 min) | `RuntimeError` (raise `llm.timeout` if expected) |
| Empty stdout | `RuntimeError` with the exit code + stderr tail |
| Envelope `error` / no `response` | `RuntimeError` with the error message |
| Reply is not JSON | `RuntimeError` (logged with the raw reply) |
| Schema validation failure | `RuntimeError` from `output_schema.model_validate()` |

## Read-only & headless

Gemini downgrades a stricter approval mode to `default` in a directory it doesn't trust,
which would make a headless run prompt (and hang) or run unconstrained. The harness passes
`--skip-trust` so `--approval-mode plan` holds for the session — the CLI stays read-only
without an interactive trust prompt. Junior's runbook is the single source of the prompt,
so a run behaves the same on every machine.
