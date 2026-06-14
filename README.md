# Junior — hand any task to an AI junior

Junior runs **runbooks**: deterministic collect → **one schema-validated LLM call** → deterministic publish. Code review is the built-in flagship — for GitLab MRs, GitHub PRs, and Bitbucket Data Center PRs, locally or in CI — but the framework assumes nothing about code: a YAML manifest turns any prompt + shell command into a runbook of your own.

Two independent extension points — **runbooks** (`local_review` / `github_pr_review` / `gitlab_pr_review` / `bitbucket_pr_review`, `weather_advice`, or your own module/YAML) and **harnesses** (`claudecode` / `codex` / `pydantic` / `deepagents` / `pi`, incl. local models) — one config priority chain: flags → env → YAML config.

## Install

The core install is lean — just the CLI plus the default `claudecode` harness (no LLM
SDKs, since `claudecode` drives the `claude` CLI). Add an **extra** for every harness or
platform you actually use; extras compose in one bracket.

```bash
# Core — runs `junior run` with the default claudecode harness out of the box
uv tool install "junior @ git+https://github.com/mishachepi/junior.git"

# Pick what you need (extras compose: junior[gitlab,codex])
uv tool install "junior[codex]      @ git+https://github.com/mishachepi/junior.git"  # codex harness
uv tool install "junior[pydantic]   @ git+https://github.com/mishachepi/junior.git"  # pydantic-ai harness
uv tool install "junior[deepagents] @ git+https://github.com/mishachepi/junior.git"  # LangChain stack
uv tool install "junior[gitlab]     @ git+https://github.com/mishachepi/junior.git"  # GitLab MR metadata
uv tool install "junior[github]     @ git+https://github.com/mishachepi/junior.git"  # GitHub PR metadata
uv tool install "junior[bitbucket]  @ git+https://github.com/mishachepi/junior.git"  # Bitbucket DC PR metadata
uv tool install "junior[all]        @ git+https://github.com/mishachepi/junior.git"  # everything

# Multiple harnesses + a platform in one go
uv tool install "junior[codex,pydantic,gitlab] @ git+https://github.com/mishachepi/junior.git"
```

From a local clone: `git clone … && cd junior && uv tool install ".[codex,gitlab]"`

### What each extra pulls

| Extra | Python deps it adds | Also needs (not pip) |
|-------|---------------------|----------------------|
| *(core)* | — | `claude` CLI for the default harness |
| `codex` | `openai` (strict-schema helper) | `codex` CLI + auth |
| `pydantic` | `pydantic-ai-slim[anthropic,openai]` | `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` |
| `deepagents` | `deepagents` + LangChain stack | `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` |
| `gitlab` | `python-gitlab` | `GITLAB_TOKEN` |
| `github` | `httpx` | `gh` CLI + `GITHUB_TOKEN` |
| `bitbucket` | `httpx` | `BITBUCKET_*` env vars (token, url, project, repo, PR id) |
| `all` | everything above | — |

Install only the harness you run and you skip every other harness's SDK — e.g. a
`claudecode`-only or `codex`-only setup never pulls the heavy `pydantic-ai` / LangChain trees.

## Quick Start

```bash
junior init                                              # one-time interactive setup
junior run                                               # your configured runbook: review the diff → stdout
junior run --prompt "Find security issues"               # inline LLM instructions, repeatable
junior run --runbook local_review "def f(uid): q(uid)"   # review pasted text — no git needed
junior run --prompt-file my-rules.md                     # prompt from a .md file, repeatable
junior run --runbook github_pr_review --publish         # review the GitHub PR + post comments
junior dry-run                                           # preview what would be reviewed (no AI)
```

`local_review` reviews the local diff (raw JSON to stdout; `--publish` renders Markdown locally); the runbook is always chosen explicitly — `junior init` sets yours. To post, pick a platform runbook (`github_pr_review` / `gitlab_pr_review` / `bitbucket_pr_review`) and add `--publish`. Split collect from review (handy across machines or for CI fan-out):

```bash
junior dry-run -o ctx.json                # collect + preview, save context (no AI)
junior run --from-file ctx.json -o review.md
junior run --runbook gitlab_pr_review --publish-file review.md   # post a saved .md, skip the runbook
```

`junior <cmd> --help` shows everything; `junior config show` prints all settings + defaults as YAML (`> .junior.yaml`), and `junior config env --harness X --runbook Y` lists the env vars that combo needs.

## How It Works

```
Collect (deterministic)    ->  Harness (the one AI step)  ->  Publish (deterministic)
-------------------------     -------------------------      -----------------------
git diff + PR metadata        claudecode (CLI)               stdout / file / JSON pipe
a shell command's stdout      codex (CLI)                    PR / MR comments
live API data                 pydantic (SDK)                 a terminal panel
stdin from another junior     deepagents (LangChain)         any shell command
                              pi (CLI - local models)
```

Every run also drops a secret-free JSON record at `.junior/output/{timestamp}.json` (disable with `--no-record`). See the [full documentation](https://junior.mchep.dev) for CLI reference, configuration, CI setup, and more.

## Beyond code review

Nothing in the framework assumes "diff" or "PR". A YAML manifest in `.junior/runbooks/` is a complete runbook — and juniors chain through pipes, so one can do the task and the next one check it:

```yaml
# .junior/runbooks/standup/standup.yaml
system_prompt: Summarize this git log as a short standup update.
collect: git log --since=yesterday --oneline
```

```bash
junior run --runbook standup                                      # validated JSON to stdout
junior run --runbook triage | junior run --runbook gatekeeper --publish   # a pipeline of juniors
```

See [Runbooks in YAML](https://junior.mchep.dev/script_runbooks/) and [Philosophy](https://junior.mchep.dev/philosophy/).

## Docs

Full docs live at **<https://junior.mchep.dev>** (source: `docs-site/src/content/docs/`).

| Doc | Description |
|-----|-------------|
| [Getting Started](https://junior.mchep.dev/getting_started/) | Guided five-minute onboarding |
| [Use cases](https://junior.mchep.dev/use_cases/) | Six ready-made scenarios: CI gates, YAML runbooks, junior pipelines, local models |
| [Philosophy](https://junior.mchep.dev/philosophy/) | The vision: a deterministic LLM wrapper, and why it's called "Junior" |
| [Runbooks in YAML](https://junior.mchep.dev/script_runbooks/) | Manifest runbooks + chaining juniors through pipes |
| [Glossary](https://junior.mchep.dev/glossary/) | Every entity — runbook, harness, models, settings — defined |
| [CLI Reference](https://junior.mchep.dev/cli/) | All subcommands, flags, source modes, examples |
| [Configuration](https://junior.mchep.dev/configuration/) | Env vars, API keys, YAML config, tuning |
| [Prompts](https://junior.mchep.dev/prompts/) | Supplying prompts via `--prompt` / `--prompt-file` / config |
| [CI Setup](https://junior.mchep.dev/ci/) | GitLab CI, GitHub Actions, Docker |
| [Architecture](https://junior.mchep.dev/architecture/) | Runbook × harness, registry, project layout |
| [Choosing a harness](https://junior.mchep.dev/agent_backends/) | Which LLM driver fits: comparison + recommendations |
| [Adding Runbooks & Harnesses](https://junior.mchep.dev/adding_backends/) | Add a runbook (4 ways) or a harness |
| [FAQ](https://junior.mchep.dev/faq/) | Common questions and troubleshooting |
| [Runbook Example](https://junior.mchep.dev/runbook_example/readme/) | End-to-end walkthrough with real data |
| [CHANGELOG](CHANGELOG.md) | Versioned changes and breaking-change migration |
| [ROADMAP](ROADMAP.md) | Planned features and known issues |
