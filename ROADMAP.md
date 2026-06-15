# Roadmap

## Known Issues

### DeepAgents harness (deprecated)

`deepagents` is **deprecated** — the least reliable harness; selecting it now
prints a deprecation warning. Kept for one more version, but prefer `pydantic`:

- Fails on large diffs (>30KB) — timeout or the orchestrator skips `submit_review`.
- With a single prompt (the common case) the orchestrator can get lost and never
  call `submit_review`.
- No retry logic for provider rate limits.

Prefer `claudecode` (default), `codex`, or `pydantic` for production use.

### CLI

- `parse_kv` (`--context` / `--context-file`) strips surrounding whitespace from
  keys and values, and a duplicate `KEY=` silently overwrites the earlier one.

## Planned

### Security (prompt injection)

- Prompt allowlist per repo (`.junior/allowed_prompts.txt`).
- Prompt signature verification for CI.
- Sandboxed prompt mode: external prompts can only add criteria, not override
  base rules.
- Audit log for prompts used per review.
- Path restrictions for `--config` and `--prompt-file` in CI mode.

See [prompt injection](docs-site/src/content/docs/prompt_injection.md) for the
current mitigations.

### Prompts (`--prompt-file`)

- Prompt validation: warn on missing frontmatter, empty body, excessive size.
- Prompt composition: `extends:` to inherit a base prompt.

### Parallel prompt fan-out

Today multiple `--prompt` entries are concatenated into one system prompt and the
harness runs **once**. Planned: each prompt becomes its own independent harness
run (`--prompt "security audit" --prompt "logic review"` → two parallel calls,
each unaware of the other), with the runner doing the fan-out. Open design
questions before this lands:

- **Publish semantics** — N runs produce N outputs; the runbook decides what
  publishing means: merge the outputs into one publish, or publish each
  separately.
- Exit code, usage accounting, and the run record across N results.

### Harness tools / MCP pass-through

Today each agent harness runs in a locked-down deterministic mode with a fixed
flag set — `claudecode` and `pi` get a restricted read-only tool allowlist, `pi`
disables extensions/skills/prompt-templates, and no MCP config is passed (only
`codex` reads its own `~/.codex/config.toml`). Planned: an opt-in escape hatch to
extend the agentic surface per harness — extra MCP servers, additional tools, and
harness-specific settings/plugins — configured in `.junior.yaml` (e.g.
`llm.harness_args` / a per-harness `mcp:` block). This is aimed at the Junior
**Docker image**, where the harness CLI runs in a controlled environment: the
image can ship and wire up MCP servers/tools, so a containerized review can reach
issue trackers, docs, or internal services while the host install stays minimal
and deterministic by default. Open question: how much this erodes determinism, so
it stays strictly opt-in.

### Output

- Round-trip the structured result: save a runbook's JSON output and later
  `--publish` it (parse the saved `LLMReviewOutput` and post inline comments to
  GitLab/GitHub), so collect/review/publish can run on different machines without
  re-rendering. Today `--publish-file` posts a pre-rendered `.md` only.

### DeepAgents

- Diff chunking for large diffs.
- Fix the single-prompt orchestrator so it reliably calls `submit_review`.
- Retry logic for rate limits.

### Other

- Silent mode (suppress non-essential stderr).
- Make `PROJECT_DIR` explicit/required for git runbooks.
