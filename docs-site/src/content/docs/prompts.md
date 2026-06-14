---
title: "Prompts"
---

# Prompts

Junior ships no *task* prompts — you provide the instructions yourself (code_review adds only its base review rules: severity scale, focus on the diff). Three ways that all stack:

| Source | How |
|--------|-----|
| Inline | `--prompt "Check security issues"` (repeatable) |
| File | `--prompt-file path/to/rules.md` (repeatable). Sugar for `--prompt file://<abs>` |
| Config | `context.prompts` — one list, each entry is inline text or `file://...` URI |

CLI flags **append** to config values — you can keep a baseline in config and add ad-hoc instructions on the command line. Empty is fine too: the LLM still gets the diff, MR metadata, prior discussion, and project instructions from `AGENT.md` / `CLAUDE.md`.

## Examples

Inline only:

```bash
junior run \
  --prompt "Find security vulnerabilities — auth bypass, secrets, injection" \
  --prompt "Check error handling and edge cases"
```

File + inline:

```bash
junior run \
  --prompt-file ./rules/api-standards.md \
  --prompt "Pay extra attention to the new caching layer"
```

Config + CLI:

```yaml
# .junior.yaml
context:
  prompts:
    - file://./prompts/security.md       # resolved relative to this file
    - "Check error handling and edge cases"
```

```bash
# Runs: security.md + the inline config prompt + the ad-hoc CLI one
junior run --prompt "Focus on the migration script in this MR"
```

## file:// URIs in config

Inside a config file (`.junior.yaml`, `--config foo.yaml`, global config), `context.prompts` entries that start with `file://` point at a `.md` file:

- **Relative** URI (`file://./prompts/x.md`, `file://prompts/x.md`) resolves against **the config file's own directory** — so multiple presets in `.junior/*.yaml` can each reference `file://./prompts/foo.md` without ambiguity.
- **Absolute** URI (`file:///abs/path/x.md`) is used as-is.
- Anything else is treated as inline prompt text.

CLI `--prompt-file foo.md` is just a shortcut: junior converts the path to an absolute `file://...` URI and appends to the same list.

## Prompt file format

Plain `.md` works. Frontmatter is optional — useful for readable logs:

```markdown
---
name: api-standards
description: API design rules for our team
---

You are an expert reviewing REST API code...
```

Without frontmatter, the file's stem is used as the name.

## Example prompts

See [`examples/prompts/`](examples/prompts/) for five reference prompts you can copy and adapt:

- `security.md` — auth/authz bypass, TOCTOU, path traversal, hardcoded secrets
- `logic.md` — wrong conditionals, missing edge cases, error handling
- `design.md` — misleading names, DRY/KISS/SRP, O(n²), N+1 queries
- `docs.md` — docs gaps for new features, flags, APIs
- `common.md` — all of the above in one prompt (cheaper than running them separately)

Drop them into your repo or `~/.junior/`, then reference with `--prompt-file`:

```bash
junior run --prompt-file ./prompts/security.md --prompt-file ./prompts/logic.md
```

## One system prompt, one call

All prompt bodies are merged into a **single** system prompt and the harness runs
**once** — there is no per-prompt fan-out. How each harness then reaches the model and
the diff (inlined vs read via file tools) is covered in
[Choosing a harness](agent_backends.md).

## What the LLM sees

### System prompt

1. **Prompt body** — from `--prompt`, `--prompt-file`, or `context.prompts` in the config
2. **Base rules** — shared instructions: focus on changed code, be constructive, use `request_changes` only for critical/multiple high issues
3. **Project instructions** — first found file from the repo root: `AGENT.md`, `AGENTS.md`, `CLAUDE.md`. Loaded verbatim up to 30k chars (`MAX_INSTRUCTIONS_CHARS`); anything beyond is truncated with a warning. **Security note:** read from the working tree, not target branch — a malicious MR can modify them. See [Security](prompt_injection.md)

### User message

Built by `build_user_message()` from collected context:

1. **MR metadata** — title, description, source→target branch, labels
2. **Extra context** — from `--context` and `--context-file` flags
3. **Commit messages** — list of commits in the MR
4. **Prior discussion** — human comments on the MR/PR (general notes + inline review threads), fetched on each iteration so the agent can see what reviewers already raised and avoid duplicating feedback that was addressed. System notes are filtered; capped at 50 newest (`MAX_COMMENTS`). Marked as untrusted input — see [Security](prompt_injection.md)
5. **Changed files list** — paths with status (added/modified/deleted)
6. **Code diff** — full unified diff, inlined while ≤ 50k chars (`INLINE_DIFF_MAX_CHARS`); above that, file-access harnesses fall back to "read the changed files via your tools"

### What is NOT sent in the user message

- File contents (agents can read files via tools if needed)
- Unchanged files (unless the harness explores them via its file tools)
- Git history beyond the diff
- CI environment variables, API keys, or tokens

## Where the review goes

Without `--publish` the raw JSON result goes to stdout/`-o`; with `--publish` the
runbook's custom publish runs instead. Details:
[CLI → Publish vs raw output](cli.md#publish-vs-raw-output).
