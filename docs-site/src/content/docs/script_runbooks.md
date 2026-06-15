---
title: Runbooks in YAML
---

# Runbooks in YAML

A runbook is the **task you hand to Junior**: the instruction (system prompt), where the
input comes from (collect), the shape of the answer (schema), and what to do with it
(publish). You don't need Python for any of that — a small YAML **manifest** in your
repository is enough, and each phase is an ordinary shell command in any language.

This page is the five-minute path from "I have a task" to a working runbook, plus the
recipe for chaining several Juniors into a pipeline.

## The minimal runbook

One folder, one file:

```yaml
# .junior/runbooks/summarize/summarize.yaml
system_prompt: |
  Summarize the input in three bullet points.
  Be concrete; keep code identifiers verbatim.
```

Enable repo-local runbooks and run it:

```yaml
# .junior.yaml
local_runbooks: true
```

```bash
git log --oneline -20 | junior run --runbook summarize
```

That's a complete runbook. Everything you didn't specify has a default:

- **input** — no `collect` command, so the user message is the positional argument if
  given (`junior run --runbook summarize "some text"`), else whatever you **pipe into
  Junior's stdin** (on an interactive terminal with nothing piped it's empty);
- **output schema** — `{"result": "<string>"}`, so the run still emits validated JSON;
- **publish** — none; the raw result JSON goes to stdout / `-o FILE`, pipe-safe.

## The full manifest

```yaml
# .junior/runbooks/ansible-report/ansible-report.yaml
name: ansible_report               # default: the folder name
description: analyze a play run, draft a Jira comment

system_prompt: prompt.md           # path (relative to the manifest) or inline text

schema:                            # JSON-Schema for the AI result — path or inline.
  type: object                     # Omit it → {"result": "<string>"}
  required: [status, jira_comment]
  properties:
    status: {type: string, enum: [ok, degraded, failed]}
    jira_comment: {type: string}

collect: ./run-play.sh             # stdout = the user message the AI sees.
                                   # Omit it → the user message is read from Junior's STDIN.

publish: ./post-jira.sh            # gets the validated result JSON on STDIN.
                                   # Runs only with --publish; omit it → JSON is printed.

needs_git: false                   # true = preflight requires a .git directory
blocking: false                    # true = exit code 1 (fail CI) on every result
```

A manifest needs at least a `system_prompt` or a `collect` — everything else is optional.

Key facts about the commands:

- `collect`'s stdout is used **verbatim** as the user message. It does **not** have to be
  JSON — a playbook log, a diff, a config file, plain prose are all fine. JSON with a
  schema is required only on the *output* side; that contract is what makes results
  machine-readable and chains reliable.
- Both commands run with `cwd` = the manifest's folder and inherit your environment plus:
  - `JUNIOR_PROJECT_DIR` — the project directory of the run;
  - `JUNIOR_CONTEXT_<KEY>` — one per `--context KEY=VAL` flag.
- A non-zero exit from either command aborts the run with the command's stderr.

The layout next to the manifest is up to you:

```
.junior/runbooks/ansible-report/
  ansible-report.yaml   # the manifest
  prompt.md             # the instruction
  run-play.sh           # runs ansible-playbook, prints the (tail of the) log
  post-jira.sh          # reads result JSON on stdin, POSTs the comment to Jira
```

> [!WARNING]
> `local_runbooks: true` executes commands shipped in the repository — same trust model
> as a `Makefile` or a git hook. Only enable it in repos you trust. See
> [prompt_injection.md](prompt_injection.md).

## Chaining Juniors into a pipeline

Without `--publish`, every `junior run` prints exactly one JSON document matching the
runbook's schema — nothing else on stdout. A runbook **without a `collect` command reads
its user message from stdin**. Those two rules compose into ordinary shell pipelines:

```bash
junior run --runbook ansible_report \
  | junior run --runbook comment_review \
  | junior run --runbook comment_gatekeeper --publish
```

Each link is an independent Junior with its own instruction, its own output schema, its
own [run record](cli.md) in `.junior/output/` (the audit trail covers every step), and —
because `--harness` is per-invocation — its own model: run the bulk step on a cheap or
local model and the final gate on a strong one.

```bash
junior run --runbook ansible_report --harness pydantic --model openai:gpt-4o-mini \
  | junior run --runbook comment_gatekeeper --harness claudecode --publish
```

The downstream runbook's `system_prompt` should say what the input is, e.g.:

```yaml
# .junior/runbooks/comment-gatekeeper/comment-gatekeeper.yaml
system_prompt: |
  STDIN carries JSON from a previous step: {"status": ..., "jira_comment": ...}.
  Verify the comment states facts consistent with the status, fix the tone,
  and return the final comment text.
schema:
  type: object
  required: [approved, final_comment]
  properties:
    approved: {type: boolean}
    final_comment: {type: string}
publish: ./post-jira.sh
```

Orchestration stays where it belongs — your shell, Makefile, or CI job. Junior itself
remains a deterministic single step: same input, same prompt, one validated JSON out
(see [Philosophy](philosophy.md)).

> [!TIP]
> Debug a chain link-by-link: `junior dry-run --runbook X` shows the exact system prompt
> and user message the harness would get (pipe into it to test the stdin mode), and
> `junior runs last | jq .output` replays the previous link's output without paying for
> a new LLM call.

## Distribution

Repo-local manifests are one of four ways to add a runbook (built-in, pip entry-point,
`--runbook pkg.module:Class`, repo-local) — see
[Adding a runbook](adding_runbooks.md). A complete copy-paste example
(weather → what to wear, scripts in `python3`, no API key) lives in
[`examples/runbooks/weather/`](examples/runbooks/weather/).

The machinery is `src/junior/runbooks/script/runbook.py` (`ScriptRunbook`); manifests are
discovered by `registry.load_local_runbooks()` under `<project>/.junior/runbooks/`.
