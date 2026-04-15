# Junior

AI code review agent for GitLab MRs and GitHub PRs.

## Quick Reference

- **Entry point**: `src/junior/cli.py:main()`
- **Config**: `src/junior/config.py` — `Settings` (pydantic-settings, frozen), JSON config loading
- **Setup**: `src/junior/init_config.py` — interactive `--init` wizard (questionary)
- **Models**: `src/junior/models.py` — `CollectedContext`, `ReviewResult`, `ReviewComment`
- **Pipeline**: collect (`collect/`) → review (`agent/`) → publish (`publish/`)
- **Dispatch**: enum value = module path, `importlib.import_module(backend.value)`
- **Tests**: `uv run pytest tests/ -v`
- **Lint**: `uv run ruff check src/`

## Key Patterns

- Each phase (collect, agent, publish) has `core/` with shared utilities and `__init__.py` with dispatch
- All backends share: `build_review_prompt()` (prompt body + BASE_RULES + project instructions)
- New backend = one file + one enum member in `config.py`. See `docs/adding_backends.md`
- Platform auto-detection: token presence → collector + publisher (GITLAB_TOKEN / GITHUB_TOKEN / neither)
- Config hierarchy: CLI flags → env vars → --config FILE → .junior.json → ~/.config/junior/config.json
- Default backend: `claudecode` (no API key needed, uses Claude CLI)

## Project Structure

```
src/junior/
  __init__.py            ← package init, exports __version__
  __main__.py            ← python -m junior entry point
  cli.py                 ← CLI: parse args → collect → review → publish
  config.py              ← Settings (frozen), backend enums, auto-detection
  models.py              ← Pydantic data models (frozen)
  prompt_loader.py       ← load prompts/*.md with frontmatter

  collect/               ← Phase 1: deterministic collection
    __init__.py          ← dispatch via resolved_collector
    local.py             ← no API enrichment
    gitlab.py            ← + GitLab MR metadata via python-gitlab
    github.py            ← + GitHub PR metadata via httpx
    core/
      collect.py         ← collect_base(), enrich_with_metadata()
      diff.py            ← git diff, parse, commit messages

  agent/                 ← Phase 2: AI review
    __init__.py          ← dispatch via agent_backend
    pydantic.py          ← parallel sub-agents + summary agent via pydantic-ai
    claudecode.py        ← claude -p subprocess with JSON schema output
    codex.py             ← codex exec subprocess
    deepagents.py        ← LLM orchestrator + subagents via langchain
    core/
      context_builder.py ← build user message from CollectedContext
      instructions.py    ← read AGENT.md / CLAUDE.md, BASE_RULES

  publish/               ← Phase 3: post results
    __init__.py          ← dispatch via resolved_publisher
    local.py             ← stdout or file output
    gitlab.py            ← MR note + inline discussion threads
    github.py            ← PR comment + review comments
    core/
      formatter.py       ← markdown formatting, format_summary(), format_inline_comment()

  prompts/               ← built-in review prompt files
    security.md
    logic.md
    design.md
    docs.md
    common.md
```

## Code Conventions

- Python 3.12+, ruff, line length 100
- Pydantic models with `frozen=True`
- structlog for logging (not stdlib logging)
- Error handling: `logger.error(..., error=str(e))` for warnings, raise for fatal
- Lazy imports in `cli.py` for optional deps (phases import at point of use)

## Documentation

| File | Triggers | Purpose |
|------|----------|---------|
| `docs/index.md` | about, install, quick start | Overview, installation, default command |
| `docs/cli.md` | CLI, flags, arguments, source modes | CLI reference, all flags, examples |
| `docs/configuration.md` | env vars, config, tokens, JSON | Environment variables, API keys, tuning |
| `docs/prompts.md` | prompts, custom prompts, what LLM sees | Built-in/custom prompts, per-backend behavior |
| `docs/ci.md` | CI, GitLab, GitHub Actions, docker | CI setup for GitLab and GitHub |
| `docs/architecture.md` | architecture, pipeline, structure, dispatch | Pipeline diagram, enum dispatch, project structure |
| `docs/agent_backends.md` | backend, comparison, choose | Backend comparison table |
| `docs/agent_backends/*.md` | specific backend details | Per-backend architecture docs |
| `docs/adding_backends.md` | add backend, new backend, extend | How to add/remove backends |
| `docs/prompt_injection.md` | security, prompt injection, attack | Prompt injection risks and mitigations |
| `docs/faq.md` | FAQ, troubleshooting, questions | Common questions and troubleshooting |
| `docs/pipeline_example/` | pipeline example, walkthrough | Step-by-step full pipeline run |
| `ROADMAP.md` | roadmap, future, planned | Planned features and improvements |

## Documentation Update Plan

When changing code, update the corresponding docs:

| What changed | Update these docs |
|-------------|-------------------|
| CLI flags (`_parse_args()`) | `docs/cli.md`, `docs/index.md` (if affects defaults) |
| Settings fields (`config.py`) | `docs/configuration.md` |
| Prompts (`prompts/*.md`) | `docs/prompts.md` |
| New/removed backend | `docs/agent_backends.md`, `docs/adding_backends.md`, `docs/architecture.md` |
| Pipeline flow (collect/review/publish) | `docs/architecture.md` |
| CI config or Docker | `docs/ci.md` |
| Exit codes | `docs/index.md` |
| Security model | `docs/prompt_injection.md` |
| Install method or deps | `docs/index.md`, `README.md` |
| Any user-facing change | Check `docs/faq.md` for relevance |
