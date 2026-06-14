# Junior

A **runbook framework** for AI "juniors" — deterministic collect → one schema-validated LLM call → deterministic publish. Code review (GitLab / GitHub / Bitbucket DC) is the built-in flagship, not the boundary. Two concepts explain the whole codebase:

- **Runbook** (`Runbook[Ctx, Result]` ABC) — a module owning one vertical: collect → render → harness → publish, plus its context/result schemas. The platform (local / GitHub / GitLab / Bitbucket DC) is part of the runbook, not a separate selector.
- **Harness** (`Harness` ABC) — the schema-agnostic LLM driver: `complete(*, system_prompt, user_message, output_schema, settings) -> LLMResult`. Five built-ins: `claudecode` (default), `codex`, `pydantic`, `deepagents`, `pi` (local models).

Both ABCs live in `src/junior/runbook/base.py`. The big picture is documented — read it instead of re-deriving: [architecture](docs-site/src/content/docs/architecture.md), [glossary](docs-site/src/content/docs/glossary.md), [philosophy](docs-site/src/content/docs/philosophy.md).

## Commands

- Tests: `uv run pytest tests/ -q`
- Lint: `uv run ruff check src/ tests/`
- Docs site: `cd docs-site && npm run build` (dev: `npm run dev` → <http://127.0.0.1:8181>)

## Project structure

```
src/junior/
  cli/            ← Typer surface: run, dry-run, runs, config {init,list,show,env,path}; app.py:main() is the entry point
  interactive/    ← questionary wizards for `junior init` and `junior run -i`
  config.py       ← Settings = ContextSettings + LLMSettings + OutputSettings (+ top-level runbook/log_level); frozen
  init_config.py  ← the `junior init` wizard
  runbook/        ← framework core (domain-agnostic): base.py (both ABCs), registry.py (discovery), runner.py
  harnesses/      ← LLM drivers, one file each, exposing HARNESS: claudecode, codex, pydantic, deepagents, pi
  runbooks/       ← built-ins (auto-discovered): code_review/{local,github,gitlab,bitbucket}, weather (example), script (YAML manifests)
  collect/        ← context-collection helper libs the runbooks call: local/gitlab/github/bitbucket + core/
  publish/        ← result-posting helper libs: local/gitlab/github/bitbucket + core/ (formatter)
  run_record.py   ← writes the .junior/output/{ts}.json trace after each run
  prompt_loader.py, github_api.py, bitbucket_api.py
  models.py       ← DEPRECATED re-export shim → runbooks/code_review/models.py
tests/            ← pytest; harness contract tests are parametrized over HarnessKind, so a new harness is covered automatically
docs-site/        ← Astro + Starlight docs site; deployed to GitHub Pages by .github/workflows/docs.yml
```

## Rules that bite

- **Output contract (all runbooks):** without `--publish` → the raw result JSON goes to stdout/`-o` (pipe-safe); with `--publish` → only the runbook's `publish()` runs. Logs always go to stderr (structlog); user-facing output goes through rich (`cli/console.py`). Reference: [cli.md](docs-site/src/content/docs/cli.md).
- **Lazy imports:** runbook and harness modules import their platform/SDK deps *inside* methods (`collect` / `_post_to_platform` / `complete`) — registry scans and `junior list` must stay cheap on a core install. `Harness.is_ready()` does env/CLI checks only, no heavy imports.
- **Domain models** live in `src/junior/runbooks/code_review/models.py`. `junior.models` is a deprecated shim — never import it in new code.
- **Config is YAML-only.** Priority: CLI flags → env → `--config FILE` → `./.junior.{yaml,yml}` (found walking up to the repo root) → `~/.config/junior/settings.{yaml,yml}`. Shorthands `harness`/`model`/`publish`/`output_file` are accepted at the config root. Reference: [configuration.md](docs-site/src/content/docs/configuration.md).
- Pydantic models are `frozen=True`; logging is structlog only (never stdlib); Python 3.12+, ruff, line length 100.
- Exit codes: 0 ok · 1 blocking findings · 2 config error · 3 runtime error.
- **Adding a harness or runbook:** follow [adding_backends.md](docs-site/src/content/docs/adding_backends.md) — it lists every registration touchpoint (HarnessKind enum, HARNESS_META, validation skip list, extras).

## Documentation map

All user docs live in `docs-site/src/content/docs/` (single source of truth, published at <https://junior.mchep.dev>). Look things up there before answering questions or re-deriving behavior:

| Page | What's there |
|------|--------------|
| [index.mdx](docs-site/src/content/docs/index.mdx) | Landing page (splash, MDX): hero + 4 use-case cards, how it works, install table, getting-started pointer — deliberately short |
| [getting_started.md](docs-site/src/content/docs/getting_started.md) | Guided 5-minute onboarding (has 🎥 video placeholders) |
| [use_cases.md](docs-site/src/content/docs/use_cases.md) | Six selling scenarios, each with a ready command/manifest |
| [philosophy.md](docs-site/src/content/docs/philosophy.md) | The vision + why it's called "Junior" |
| [glossary.md](docs-site/src/content/docs/glossary.md) | Definition of every entity (runbook, harness, models, settings) |
| [cli.md](docs-site/src/content/docs/cli.md) | Per-subcommand reference, all flags, source modes |
| [configuration.md](docs-site/src/content/docs/configuration.md) | Settings groups, env vars, config priority, harness reference |
| [prompts.md](docs-site/src/content/docs/prompts.md) | Supplying prompts; what the LLM sees ([examples/prompts/](docs-site/src/content/docs/examples/prompts/)) |
| [ci.md](docs-site/src/content/docs/ci.md) | CI recipes: GitLab CI, GitHub Actions, Bitbucket DC (Jenkins) |
| [architecture.md](docs-site/src/content/docs/architecture.md) | Diagrams, flow, project layout ([architecture/runbooks.md](docs-site/src/content/docs/architecture/runbooks.md) = framework deep dive) |
| [agent_backends.md](docs-site/src/content/docs/agent_backends.md) | "Choosing a harness": decision table + comparison ([agent_backends/*.md](docs-site/src/content/docs/agent_backends/) = per-harness deep dives, under Architecture in the sidebar) |
| [script_runbooks.md](docs-site/src/content/docs/script_runbooks.md) | YAML manifest runbooks + `junior run \| junior run` chaining |
| [adding_backends.md](docs-site/src/content/docs/adding_backends.md) | How to add a harness or runbook |
| [prompt_injection.md](docs-site/src/content/docs/prompt_injection.md) | Security model |
| [faq.md](docs-site/src/content/docs/faq.md) | Troubleshooting |
| `CHANGELOG.md` / `ROADMAP.md` | Versioned changes + what's planned |

## When code changes, update the docs

| What changed | Update |
|-------------|--------|
| CLI flags / subcommands (`src/junior/cli/`) | `cli.md` |
| Settings fields (`src/junior/config.py`) | `configuration.md` |
| Harness added/removed/changed | `agent_backends.md` (+ its subpage), `adding_backends.md`, `architecture.md`, `configuration.md` (harness reference), `glossary.md` |
| Runbook added/removed/changed | `cli.md`, `architecture.md`, `adding_backends.md`, `ci.md` (if platform) |
| Exit codes | `cli.md`, `getting_started.md` |
| Install method or deps | `index.md`, `README.md` |
| Breaking change | `CHANGELOG.md` + every doc showing the old shape |
| New/renamed/moved doc page | `starlight.sidebar` in `docs-site/astro.config.mjs` |
| Any user-visible change | check `faq.md` for relevance |

Docs authoring: every page needs a frontmatter `title`; cross-link with relative `*.md` paths; GitHub callouts (`> [!NOTE]`) and ` ```mermaid ` blocks work; a remark plugin strips the body `# H1` and rewrites links. Details: `docs-site/README.md`.
