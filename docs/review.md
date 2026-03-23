# Junior — Development Notes

## Test Results (hello world MR, 4 files, 140 lines)

| Backend | Model | Prompts | Findings | Tokens | Recommendation |
|---------|-------|---------|----------|--------|----------------|
| codex | gpt-5.3-codex | common | 0 | 22,476 | approve |
| pydantic | gpt-4o-mini | sec+logic+design | 9 | 13,938 | comment |
| pydantic | gpt-5.4 | sec+logic+design | 0 | 5,297 | approve |
| pydantic | gpt-5.4 | common | 4 | 3,100 | request_changes |
| deepagents | gpt-5.4 | sec+logic+design | 1 | 88,528 | comment |
| deepagents | gpt-5.4 | sec+logic+design | 0 | 88,528 | approve |

## Key Findings

1. **Pydantic + gpt-5.4 is the sweet spot**: 3-5K tokens, parallel agents, structured output
2. **Model matters more than backend**: gpt-4o-mini generates noise (9 findings on hello world), gpt-5.4 is precise
3. **DeepAgents is 17x more expensive**: orchestrator overhead (~80% tokens on reasoning + file exploration)
4. **Prompts are the lever**: adding 2 lines about "dependency issues" to design.md made pydantic find the pytest-in-requirements bug

## Hidden Bug Detection (complex MR, 13 intentional bugs)

Pydantic + gpt-5.4 + security,logic,design found **11/13** bugs:

| Found | Bug |
|-------|-----|
| yes | DRY: greet_many/farewell_many don't reuse greet()/farewell() |
| yes | Security: path traversal in load_contacts |
| yes | Logic: TOCTOU race in send_greetings |
| yes | Logic: format_greeting → None for unknown styles |
| yes | Logic: ZeroDivisionError on empty list |
| yes | Security: md5 generate_id not unique |
| no | Logic: rate_limit race + silent None |
| no | Logic: sanitize_name strips hyphens |
| no | Logic: validate_email terrible |
| yes | Optimization: O(n^2) merge_contact_lists |
| yes | Security: hardcoded secrets in config.py |
| no | Design: hardcoded /tmp path |
| yes | Logic: SUPPORTED_STYLES mismatch |

## Bugs Found and Fixed During Development

| Bug | Where | Impact |
|-----|-------|--------|
| `diff.noprefix=true` breaks file parsing | collect/diff.py | 0 changed files on macOS |
| ruff returns absolute paths | collect/linter.py | lint findings don't match changed files |
| eslint returns absolute paths | collect/linter.py | same |
| `head_sha: "HEAD"` literal string | publish/gitlab.py | all inline comments fail |
| `_setup_logging` ignores log_level | cli.py | always INFO |
| `submit_review(result)` vs `**kwargs` | agent/deepagents.py | deepagents crashes |
| `CI_MERGE_REQUEST_DESCRIPTION` not a CI var | collect/ (enrichment) | description always empty |
| enricher only checked GitLab fields | collect/ (enrichment) | GitHub would never enrich |
| rich/typer unnecessary deps | cli.py | 2 extra deps for print() |
| context_files collected but never used | models.py | wasted I/O |

## Dependencies

```
Base install: 16 packages
  pydantic, pydantic-settings, python-gitlab, structlog, requests, ...

Optional extras:
  [pydantic]   → pydantic-ai-slim[anthropic,openai]
  [deepagents] → deepagents, langchain, langchain-anthropic, langchain-openai
  [codex]      → (none, codex CLI installed separately)
  [dev]        → pytest, pytest-mock, pytest-cov, ruff

Docker targets:
  pydantic → ~500MB (pydantic only)
  codex    → ~1GB   (+ Node.js + codex CLI)
  full     → ~1.1GB (all backends)
```

## Tests

84 unit tests covering:
- `test_config.py` — pydantic validators, auto-detection, preflight validation (34 tests)
- `test_collector.py` — diff parsing, noprefix handling, file status, project detection (16 tests)
- `test_formatter.py` — summary, inline comments, lint, suggestions (6 tests)
- `test_models.py` — critical_count, has_blocking_issues (5 tests)
- `test_prompt_loader.py` — discover, load, frontmatter parsing (7 tests)
- `test_integration.py` — full pipeline with mocked AI
