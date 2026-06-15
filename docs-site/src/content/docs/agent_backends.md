---
title: "Choosing a harness"
---

# Choosing a harness

A **harness** is the LLM driver — one way of calling a model. Every harness serves every
runbook (the output schema is a parameter), so picking one is purely about *how you want
the model to run*: which CLI/SDK, which auth, cloud or local. Select with `--harness`,
env `HARNESS`, or config `harness:`; default `claudecode`.

## Quick answer

| You want… | Pick | Why |
|----------|---------|-----|
| Zero-setup local reviews (default) | `claudecode` | Drives your `claude` CLI — subscription auth, git tools, explores beyond the diff |
| Predictable CI cost | `pydantic` | One structured API call, no agentic wandering |
| The OpenAI/Codex stack | `codex` | `codex exec` in a sandbox, OAuth or API key |
| **Local / offline models** | `pi` | Ollama / LM Studio / vLLM via `~/.pi/agent/models.json` — no API key, nothing leaves the machine |
| ~~To experiment with orchestration~~ | `deepagents` | **Deprecated** — LangChain orchestrator, unreliable (may skip the submit tool). Use `pydantic` instead |

## Comparison

| Harness | Install | Runs via | Auth | Status |
|---------|---------|----------|------|--------|
| `claudecode` | *(core)* | single `claude -p` subprocess | subscription or `ANTHROPIC_API_KEY` | stable |
| `codex` | `junior[codex]` | single `codex exec` in sandbox | OAuth or `OPENAI_API_KEY` | stable |
| `pydantic` | `junior[pydantic]` | single structured pydantic-ai call | API key **required** | stable |
| `deepagents` | `junior[deepagents]` | LangChain orchestrator + subagents | API key **required** | **deprecated** |
| `pi` | *(core)* | single `pi --mode json` subprocess | provider key, `auth.json`, or **none (local models)** | stable |

`junior config list harnesses` shows what's installed and ready on your machine;
`junior config env --harness X` lists the exact env vars one needs.

## How each harness works

Every harness does a **single structured call** and returns a validated instance of the
runbook's output schema. They differ in how the schema is enforced and whether the model
can read repository files itself (`file_access` — see [Glossary](glossary.md#harness)):

| | pydantic | claudecode | codex | deepagents | pi |
|--|----------|-----------|-------|------------|----|
| **Diff in user message** | Yes | No — reads files via tools | No — reads files via sandbox | Yes | Small diffs yes; tools beyond |
| **`file_access`** | `False` | `True` | `True` | `False` | `True` |
| **File tools** | `read_file`, `list_dir`, `grep` (Python) | `Read`, `Grep`, `Glob`, `Bash(git…)` (built-in) | Sandbox filesystem access | `read_file`, `ls`, `grep`, `glob` (via deepagents) | `read`, `grep`, `find`, `ls` (read-only) |
| **Output contract** | Returns the output schema instance directly | Output schema via `--json-schema` | Output schema via `--output-schema` | `submit_review` tool whose schema is the output model | Schema embedded in system prompt + validated reply |
| **Token usage** | pydantic-ai usage | CLI JSON output | CLI stderr | langchain callback | JSON event stream (per-turn usage) |

Small diffs (≤ 50k chars) are inlined for **every** harness — the diff is the review's
primary evidence; file tools serve for context beyond it.

> [!NOTE]
> `--harness` / `HARNESS` / config `harness:` is canonical. The old `--backend` /
> `BACKEND` / `backend:` is kept as a deprecated alias for one version.

## Going deeper

Per-harness internals (subprocess flags, event parsing, error handling):
[Claude Code](agent_backends/claudecode.md) · [Codex](agent_backends/codex.md) ·
[Pydantic AI](agent_backends/pydantic.md) · [DeepAgents](agent_backends/deepagents.md) ·
[Pi](agent_backends/pi.md). Writing your own is one file —
[Adding runbooks & harnesses](adding_backends.md).
