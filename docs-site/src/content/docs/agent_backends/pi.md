---
title: "Harness: Pi CLI"
---

# Harness: Pi CLI

**File:** `src/junior/harnesses/pi.py`
**Env var:** `HARNESS=pi`
**Dependencies:** `pi` CLI (`npm install -g @earendil-works/pi-coding-agent`) — no Python extra (core install)
**Auth:** any pi provider — env key (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, …), `~/.pi/agent/auth.json`, **or none at all for local models**

## Why pi

[Pi](https://github.com/badlogic/pi-mono) is a minimal, provider-agnostic coding agent.
Its standout feature for Junior is **first-class local models**: declare an
Ollama / LM Studio / vLLM endpoint once in `~/.pi/agent/models.json` and any runbook can
run on it — no API key, no cloud:

```json
{
  "providers": {
    "ollama": {
      "baseUrl": "http://localhost:11434/v1",
      "api": "openai-completions",
      "apiKey": "ollama",
      "models": [{ "id": "qwen2.5-coder:7b" }]
    }
  }
}
```

```bash
junior run --harness pi --model ollama/qwen2.5-coder:7b
```

`--model` accepts pi's `provider/id` pattern; without it pi uses its own configured
default model.

## Harness Contract

The module exposes a single `HARNESS` instance (`PiHarness`, a `Harness` subclass) with
the standard schema-agnostic method:

```python
complete(*, system_prompt: str, user_message: str,
         output_schema: type[BaseModel], settings: Settings) -> LLMResult
```

`file_access = True` — pi explores the repository with its own **read-only** tools
(`read`, `grep`, `find`, `ls`; `bash`/`edit`/`write` are excluded so a review can never
mutate the repo). The code-review runbook still inlines the diff while it's small
(≤ 50k chars); the tools serve for context beyond it.

## Architecture

```
complete(output_schema=…)
    │
    ▼
full_system = system_prompt + "## Output format" + JSON Schema of output_schema
    │     (pi has no native structured-output flag — the schema contract
    │      is embedded in the system prompt and enforced on our side)
    ▼
subprocess: pi --mode json
    │  --no-session                                 ← ephemeral
    │  --no-extensions --no-skills
    │  --no-prompt-templates --no-context-files     ← hermetic: the runbook owns the prompt
    │  --tools read,grep,find,ls                    ← read-only file access
    │  --system-prompt <full_system>
    │  [--model provider/id]
    │  <user_message>                               ← positional arg
    │  env: PI_OFFLINE=1                            ← no startup update checks
    │
    ▼
stdout = JSON event lines (session, message_end, agent_end, …)
    │
    ▼
_last_assistant(stdout)
    │  text  = last assistant message's text blocks
    │  usage = Σ per-turn usage (input+cacheRead+cacheWrite / output)
    ▼
_parse_response(text, output_schema)
    │  strip fences → extract outermost {...} → model_validate()
    ▼
LLMResult(output=<output_schema instance>, usage=Usage(...))
```

## Prompt Handling

`system_prompt` and the JSON-Schema output contract are combined into a single
`--system-prompt` value; the runbook's `user_message` is passed as one positional
argument. It's a single subprocess call — no parallelism. Because `file_access = True`,
an oversized diff is left to pi's file tools while a small one is inlined by the runbook.

## Output Format

Pi has no `--output-schema` equivalent, so the harness appends an output contract to the
system prompt («reply with ONLY one JSON object matching this JSON Schema: …») and
parses defensively: code fences are stripped, the outermost `{...}` is extracted from
any surrounding prose, then `output_schema.model_validate()` enforces the real contract.
A reply that doesn't validate fails the run — exactly like every other harness.

> [!TIP]
> This prompt-embedded-schema pattern is what makes the harness work on small local
> models too — but smaller models fail validation more often than cloud models. If a
> local model keeps failing, try a coder-tuned variant or raise `maxTokens` for it in
> `models.json`.

## File access

`file_access = True`. Pi explores the repo with **read-only** tools — `read`, `grep`,
`find`, `ls` (`--tools read,grep,find,ls`); `bash` / `edit` / `write` are deliberately
excluded so a review can never mutate the repository.

## Token Tracking

Every `message_end` event with an assistant message carries that turn's
`usage {input, output, cacheRead, cacheWrite}`. The harness sums usage across all turns
(tool loops bill each round-trip): cache reads/writes count as input. Local models
typically report zeros — the run record then shows `0` tokens, which is accurate (they
cost nothing).

## Error Handling

| Situation | Behavior |
|-----------|----------|
| pi CLI not found | `RuntimeError` with install instructions |
| Timeout (>10 min) | `RuntimeError` |
| Exit code != 0 and no assistant text | `RuntimeError` with stderr |
| No assistant message in the event stream | `RuntimeError` |
| Reply is not JSON | `RuntimeError` (logged with the raw reply) |
| Schema validation failure | `RuntimeError` from `output_schema.model_validate()` |

## Hermetic runs

Pi normally loads user extensions, skills, prompt templates, and `AGENTS.md`/`CLAUDE.md`
context files. The harness disables **all** of that: Junior's runbook is the single
source of the prompt, so a run behaves the same on every machine. Sessions are not
persisted (`--no-session`), and `PI_OFFLINE=1` suppresses startup network calls.
