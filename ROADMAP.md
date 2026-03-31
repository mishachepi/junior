# Roadmap

## Known Issues

### Documentation
- `junior --publish` without credentials fails with no clear error
- `--config` replaces `.env`, doesn't merge
- `docs/usage.md` out of sync with README (`--prompt-file`, `PROMPTS_DIR`, `PUBLISH_OUTPUT`)
- CI auto-detected variables undocumented for manual setup

### Config generation (`--config`)
- Not all fields have meaningful defaults
- `key.upper()` may not match actual pydantic-settings aliases
- CI-only variables shown in template without explanation

### CLI
- `_parse_kv_args` strips spaces in file paths; duplicate keys silently overwritten
- `--config` dual behavior (generate vs load) may confuse users

### DeepAgents
- Fails on large diffs (>30KB) — timeout or orchestrator skips `submit_review`
- With 1 prompt (common), orchestrator gets lost and doesn't call `submit_review`
- No retry logic for rate limits

## Planned

### Security (Prompt Injection)
- Prompt allowlist per repo (`.junior/allowed_prompts.txt`)
- Prompt signature verification for CI
- Sandboxed prompt mode: external prompts can only add criteria, not override built-ins
- Audit log for prompts used per review
- Path restrictions for `--config` and `--prompt-file` in CI mode

### External Prompts (`--prompt-file`)
- Prompt validation: warn on missing frontmatter, empty body, excessive size
- Prompt composition: `extends: security` to inherit built-ins

### Split Pipeline (`--collect` / `--review`)
- `junior --collect -o context.json` — run Phase 1 only, save CollectedContext as JSON
- `junior --review context.json --prompts security,logic` — load context from file, run Phase 2+3
- Enables separate CI jobs for collect and review
- Useful for debugging, caching, and running multiple reviews on same context

### Other
- Post-processing deduplication of duplicate findings across parallel agents
- `--local` flag for working-tree review mode; `--staged` for staged-only changes
- DeepAgents: diff chunking for large diffs, fix single-subagent orchestrator, retry logic
- Pydantic: token budget management per agent
