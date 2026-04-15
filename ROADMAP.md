# Roadmap

## Known Issues

### Documentation
- ~~`--config` replaces `.env`~~ ✅ done (JSON config hierarchy)
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

### Architecture
- Add `Protocol` for backend contracts (collect, review, post_review) — catch signature mismatches at type-check time instead of runtime
- Move `pydantic-ai-slim` from core dependencies to optional extra — claudecode users shouldn't need anthropic/openai SDKs

### Other
- Post-processing deduplication of duplicate findings across parallel agents
- DeepAgents: diff chunking for large diffs, fix single-subagent orchestrator, retry logic
- Add silent mode
- Make PROJECT_DIR required
