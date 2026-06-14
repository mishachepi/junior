---
title: Getting Started
description: From zero to your first AI code review in five minutes.
---

# Getting Started

Junior hands tasks to an LLM through deterministic **runbooks**; the built-in flagship —
and this walkthrough — is code review. Five minutes from zero to a structured review of
your changes. The same mechanics drive any runbook you write
([Runbooks in YAML](script_runbooks.md)).

<!-- 🎥 VIDEO 1 — "Junior in 90 seconds" (hero demo, embed here)
     Scene: a terminal in a repo on a feature branch that swaps a parameterized SQL
     query for string interpolation (an injectable query). Type `junior run --publish`,
     let the pretty Markdown review appear, zoom on the 🔴 Critical finding and the
     suggestion, then show `echo $?` → 1 ("CI would fail this").
     Keep it one take, no cuts, ~90s. This is the "what you get" moment. -->

## 1. Install

The core install is lean — the CLI plus the default `claudecode` harness, no LLM SDKs:

```bash
uv tool install "junior @ git+https://github.com/mishachepi/junior.git"
```

The default harness drives the `claude` CLI — if Claude Code is installed and logged in,
there is nothing else to set up, no API key needed.

Verify the setup — `junior list` shows every runbook and harness, with install state and
readiness:

```bash
junior list
```

```
Harnesses
claudecode     *     claude CLI subprocess (no API key)   ✓ installed · ready
codex                codex CLI subprocess                 ✗ not installed
...
```

If `claudecode` says `✓ installed · ready`, you're good. Prefer another harness —
`codex`, `pydantic`, `deepagents`, or `pi` for local models? Each is one extra away —
see the [install matrix](index.md#install) and [Choosing a harness](agent_backends.md).

<!-- 🎥 VIDEO 2 — "Install & verify" (~60s, embed here)
     Scene: empty terminal. Run the `uv tool install` line, then `junior list`.
     Point the cursor at the `✓ installed · ready` cell and at the `*` marking the
     default. No narration needed beyond captions. -->

## 2. Configure once

```bash
junior init
```

The wizard walks you through every choice and explains each one: where to save the
config (**global** `~/.config/junior/settings.yaml`, or **local** `./.junior.yaml` to
commit and share with your team), the runbook, the harness, and the output.

API keys are **never** written to the config — they stay in env vars
(`junior config env` lists exactly what your combination needs).

Check what you ended up with at any time:

```bash
junior config show     # effective config as YAML + status header
junior config path     # which config files exist and where Junior looks
```

<!-- 🎥 VIDEO 3 — "The init wizard" (~60s, embed here)
     Scene: run `junior init`, arrow through the choices (pick global, local_review,
     claudecode, no output file), show the saved-summary it prints, then run
     `junior config show` and scroll the YAML with its commented status header.
     Highlight that every wizard step has its own explanation line. -->

## 3. Your first review

> [!WARNING]
> Run Junior **from the branch with your changes**. By default it diffs
> `<target-branch>...HEAD`; on `main` itself the diff is empty and Junior exits with
> «no changes found, nothing to review».

```bash
cd /path/to/your/repo
git checkout my-feature-branch
```

Start with the free preview — `dry-run` shows the plan, the collected context, and the
**exact** system prompt + user message the harness would receive, without calling any AI:

```bash
junior dry-run
```

Happy with it? Run the real thing:

```bash
junior run               # raw structured result (JSON) → stdout
junior run --publish     # pretty Markdown review in the terminal
```

Without `--publish` you get the raw JSON — stable, pipe- and redirect-safe (logs go to
stderr, so `junior run > review.json` captures only the result). With `--publish` the
runbook renders it for humans instead:

```
## Junior Code Review

The refactor changes a parameterized SQLite query into string interpolation...

#### 🔴 Critical

- **[security]** `app.py:4` — The changed query interpolates `user_id` directly into
  SQL, replacing the previous parameterized query...
  - Suggestion: Keep the query parameterized: `db.execute("... WHERE id = ?", (user_id,))`
```

Exit code **1** means blocking findings (a critical issue or a `request_changes`
recommendation) — that's what makes CI gates work; **0** means clean. The full table is
in the [CLI reference](cli.md#exit-codes).

Steer the review with your own instructions — inline or from files, repeatable:

```bash
junior run --prompt "Focus on security and error handling"
junior run --prompt-file docs/review-rules.md
```

<!-- 🎥 VIDEO 4 — "dry-run → run → publish" (~2 min, embed here)
     Scene: on the feature branch. 1) `junior dry-run` — scroll the Plan panel and the
     user message ("this is exactly what the model will see; zero tokens spent").
     2) `junior run` — show the raw JSON shape briefly. 3) `junior run --publish` —
     the pretty Markdown. 4) `echo $?` → 1, caption "blocking finding ⇒ CI fails".
     This is the core loop; keep the planted bug the same as in VIDEO 1. -->

## 4. Every run is on the record

Each successful run writes a secret-free JSON trace to `.junior/output/` in your project
(runbook, harness, tokens, findings, the full structured output). Browse it any time:

```bash
junior runs                       # table of recent runs
junior runs last | jq .output     # newest result, pipe-safe
```

You delegated the review — the record is how you own it. Disable with `--no-record`.

## 5. Where to next

- **See what teams do with it** — six ready-made scenarios, from CI gates to
  pipelines of juniors on local models: [Use cases](use_cases.md).
- **Post to a real PR/MR — locally or as a CI gate** —
  `junior run --runbook github_pr_review --publish` (or `gitlab_pr_review` /
  `bitbucket_pr_review`); copy-paste pipelines in [CI Setup](ci.md), tokens and
  platform variables in the [FAQ](faq.md#how-do-i-review-a-remote-mr-locally).
- **Build your own runbook in YAML** — a manifest with a prompt, an optional schema,
  and two shell commands; chain several Juniors with pipes.
  [Runbooks in YAML](script_runbooks.md).
- **Tune the prompts** — instructions, the role layer, and ready-to-copy examples:
  [Prompts](prompts.md).
- **Understand the design** — why Junior is a deterministic wrapper around a
  non-deterministic worker: [Philosophy](philosophy.md).
