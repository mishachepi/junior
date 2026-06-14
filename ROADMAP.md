# Roadmap

## Known Issues

### DeepAgents harness (experimental)

`deepagents` is the least reliable harness — treat it as experimental:

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
