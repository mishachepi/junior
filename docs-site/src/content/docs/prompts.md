---
title: "Prompts & context"
---

# Prompts & context — what reaches the LLM

Every Junior run ends in **one** call to the model, and that call carries exactly **two
strings**:

- a **System Prompt** — *how* to do the job (the role, your instructions, the rules), and
- a **User Message** — *what* to work on (the diff and the facts around it).

Everything Junior gathers is sorted into one of those two. Nothing else reaches the model:
no hidden state, no file contents (unless a harness reads them with its own tools), no
environment variables or tokens.

## The whole picture

```
  THE RUNBOOK PROVIDES  (e.g. code review)    WHAT THE LLM GETS
  ────────────────────────────────────────    ─────────────────

  role  (SYSTEM_PROMPT)               ┐
  built-in review rules               ├─────►  SYSTEM PROMPT    how to do the job
                                      ┘            ▲
                                         you add: --prompt / --prompt-file

  e.g.  git diff  +  changed files    ┐
        PR/MR metadata  +  commits    ├─────►  USER MESSAGE     what to work on
        prior PR/MR comments          ┘            ▲
                                         you add: --context / --context-file
```

The **runbook provides the bulk on its own** — the left column shows what the code-review
runbook gathers; another runbook supplies its own equivalents. On top of that you inject
two things, and each has a fixed destination:

- **`--prompt` / `--prompt-file`** (or `context.prompts` in config) = *instructions* →
  **System Prompt** (“Focus on security.”).
- **`--context KEY=…` / `--context-file KEY=path`** = *named facts* → **User Message**
  (`spec=SPEC.md`, `ticket="JIRA-12 …"`).

(`[INPUT]`, the positional argument, is the *subject itself* — reviewed in place of the
git diff, or the user message for a collect-less YAML runbook.)

## What's in the System Prompt

The built-in **code-review** runbooks assemble theirs in this order (all are
recommendations to the model, not hard rules):

1. **Role** — the runbook's one-line `SYSTEM_PROMPT` (“You are a senior code reviewer…”).
2. **Your prompts** — every entry in `context.prompts`, from `--prompt`, `--prompt-file`,
   the config, or env `PROMPTS` — appended right after the role.
3. **Review rules** — the built-in `BASE_RULES`: focus on the diff, the severity scale,
   when to use `request_changes`.

That's all. The runbook does **not** read `AGENT.md` / `AGENTS.md` / `CLAUDE.md` into the
system prompt — those files live in the reviewed branch's working tree, which the diff's
author controls, so inlining them would let a PR rewrite the reviewer's instructions. A
harness that wants project memory reads it itself from its own working directory
(`claudecode` → `CLAUDE.md`, `codex` → `AGENTS.md`); the SDK harnesses
(`pydantic`/`deepagents`/`pi`) don't. See [Security](prompt_injection.md).

> A YAML or [custom runbook](adding_runbooks.md)'s system prompt is just its own
> `SYSTEM_PROMPT` plus your `context.prompts` — no review rules. You own it.

## What's in the User Message

The **collect** step builds it. For code review, in order:

1. **PR/MR metadata** — title, description, source → target branch, labels.
2. **Additional context** — your `--context KEY=text` and `--context-file KEY=path`, each
   under its key.
3. **Commits** — the commit messages in the change.
4. **Prior discussion** — existing PR/MR comments (newest 50), so the model doesn't
   re-raise resolved points. Marked **untrusted** — the model is told not to obey
   instructions written inside them ([Security](prompt_injection.md)).
5. **Changed files** — the list with status (added / modified / deleted).
6. **The diff** — the full unified diff, inlined while ≤ 50 000 chars. Above that,
   `file_access` harnesses (claudecode/codex/pi) read the changed files with their own tools
   instead; the SDK harnesses (pydantic/deepagents) still get it inlined. Either way the
   inlined diff is hard-capped at `context.max_diff_chars` (default 200 000, `0` = no cap)
   and truncated with a marker beyond that — a cost/DoS guard that applies to **every**
   harness.

**Not** sent: whole file contents (a harness may read them itself), unchanged files, git
history beyond the diff, environment variables or tokens.

> For a YAML runbook the user message is simply the stdout of its `collect` command — or
> piped stdin / the positional `[INPUT]` when there is no `collect`.

## Supplying your own instructions

Three sources, and they **stack** (CLI flags *append* to config):

| Source | How |
|--------|-----|
| Inline | `--prompt "Check for SQL injection"` (repeatable) |
| File | `--prompt-file ./rules/security.md` (repeatable) — sugar for `--prompt file://<abs>` |
| Config | `context.prompts:` — a list; each entry is inline text or a `file://…` URI |

Leaving it empty is fine: the model still gets the role, the rules, the diff, and the
metadata.

**`file://` in a config file:** a *relative* URI (`file://./prompts/x.md`) resolves against
**the config file's own directory** — so presets in `.junior/*.yaml` can each reference
`file://./prompts/foo.md` unambiguously; an *absolute* URI (`file:///abs/x.md`) is used
as-is; anything else is inline text. Prompt files are `.md`; optional frontmatter
(`name`, `description`) only makes logs readable — otherwise the filename is the name.

```yaml
# .junior.yaml
context:
  prompts:                            # → System Prompt (instructions)
    - file://./prompts/security.md    # relative to this file
    - "Pay extra attention to the migration script"
  context:                            # → User Message (= --context KEY=text)
    ticket: "JIRA-12: refactor auth"
  context_files:                      # → User Message (= --context-file KEY=path)
    spec: SPEC.md
```

```bash
junior run --runbook local_review --prompt "And the new caching layer"
# System Prompt = role + security.md + the config line + this CLI line + rules
```

The named facts you'd pass with `--context` / `--context-file` have config equivalents too
— `context.context` (inline) and `context.context_files` (key → path). Both land in the
**User Message**, not the system prompt. Note the asymmetry: `file://` URIs in
`context.prompts` resolve against the config file's directory, but `context_files` paths
are plain paths resolved against the run's working directory (write them from the repo root
in CI).

Ready-to-copy prompts (security, logic, design, docs) live in
[`examples/prompts/`](examples/prompts/).

## One system prompt, one call

All your prompt bodies merge into a **single** system prompt and the harness runs
**once** — there is no per-prompt fan-out. How each harness then reaches the model (diff
inlined vs read via file tools) is in [Choosing a harness](agent_backends.md); where the
result goes — raw JSON vs `--publish` — is in
[CLI → output](cli.md#publish-vs-raw-output).
