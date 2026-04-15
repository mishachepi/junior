# Prompts

## Built-in prompts

| Name | Focus | What it checks |
|------|-------|----------------|
| `security` | Security vulnerabilities | Auth/authz bypass, privilege escalation, TOCTOU races, path traversal, hardcoded secrets/credentials, insecure defaults, weak crypto, business logic vulns |
| `logic` | Correctness | Wrong conditionals, missing edge cases (null, empty, boundary), missing error handling, silent failures, thread safety, unreachable code, off-by-one, resource leaks |
| `design` | Code quality | Misleading names, DRY/KISS/SRP violations, O(n^2) algorithms, N+1 queries, dev deps in production, dead config flags, contract violations, hardcoded OS paths |
| `docs` | Documentation gaps | New features/flags/APIs without docs, changed behavior not reflected in docs, missing docstrings, undocumented env vars |
| `common` | All categories in one pass | Combines security + logic + design in a single prompt. Uses 1 agent instead of 3. Good for quick reviews or tight token budgets |

**`common` vs `security,logic,design`:** With `pydantic` backend, `--prompts security,logic,design` runs 3 parallel agents (one per prompt, results merged). `--prompts common` runs 1 agent covering everything. Three separate prompts are more thorough; `common` is cheaper and faster.

## Custom prompts

**Option 1**: Add .md files to `PROMPTS_DIR` and reference by name:

```bash
PROMPTS_DIR=~/.junior/prompts junior --prompts security,my_team_rules
```

**Option 2**: Pass files directly with `--prompt-file`:

```bash
junior --prompt-file ./rules/api.md --prompt-file ./rules/naming.md
```

Prompt files use frontmatter format:

```markdown
---
name: api-standards
description: API design rules for our team
---

You are an expert reviewing REST API code...
```

## How prompts are used per backend

| Backend | Behavior |
|---------|----------|
| `pydantic` | 1 parallel AI agent per prompt, results merged. Each agent gets prompt body + project instructions as system prompt. After all agents finish, a summary agent writes a 2-3 sentence overview |
| `claudecode` | All prompts concatenated into system prompt. Claude reads files via built-in tools (no diff in user message) |
| `codex` | All prompts concatenated into system prompt. Codex reads files via sandbox |
| `deepagents` | 1 subagent per prompt, LLM orchestrator coordinates |

## What the LLM sees

### System prompt

1. **Prompt body** — from built-in prompts or `--prompt-file`
2. **Base rules** — shared instructions: focus on changed code, be constructive, use `request_changes` only for critical/multiple high issues
3. **Project instructions** — first found file from the repo root: `AGENT.md`, `AGENTS.md`, `CLAUDE.md`. Loaded as-is. **Security note:** read from the working tree, not target branch — a malicious MR can modify them. See [Security](prompt_injection.md)

### User message

Built by `build_user_message()` from collected context:

1. **MR metadata** — title, description, source→target branch, labels
2. **Commit messages** — list of commits in the MR
3. **Changed files list** — paths with status (added/modified/deleted)
4. **Code diff** — full unified diff (included for `pydantic`, `deepagents`; omitted for `claudecode`, `codex` — they read files via tools instead)
5. **Extra context** — from `--context` and `--context-file` flags

### What is NOT sent in the user message

- File contents (agents can read files via tools if needed)
- Unchanged files (unless the backend explores them — `claudecode`, `pydantic`, `deepagents` all have file tools)
- Git history beyond the diff
- CI environment variables, API keys, or tokens
