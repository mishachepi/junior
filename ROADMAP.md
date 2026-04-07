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

### Other
- Post-processing deduplication of duplicate findings across parallel agents
- DeepAgents: diff chunking for large diffs, fix single-subagent orchestrator, retry logic
