# Junior — Architecture

## Overview

Junior is an AI code review agent that runs in **CI pipelines** (GitLab CI, GitHub Actions) or **locally as CLI tool**. It collects MR/PR context deterministically, delegates analysis to AI agents, and publishes structured review comments.

## Review Flow

```mermaid
flowchart TD
    A([junior CLI]) --> B

    subgraph P1["Phase 1 — Collect (deterministic)"]
        B[git diff + parse changed files] --> C[commit messages]
        C --> D["extra context\n--context (text) + --context-file (files)"]
        D --> H{platform token?}
        H -->|GITLAB_TOKEN| I[fetch MR metadata\nfrom GitLab API]
        H -->|GITHUB_TOKEN| J[fetch PR metadata\nfrom GitHub API]
        H -->|none| K[local only]
        I & J & K --> L([CollectedContext])
    end

    L --> M

    subgraph P2["Phase 2 — AI Review"]
        M[load prompts/*.md] --> N[build user message]
        N --> O{AGENT_BACKEND?}
        O -->|claudecode| Q2[claude -p subprocess\nreads files via tools]
        O -->|pydantic| P[parallel sub-agents\nvia asyncio.gather\n+ summary agent]
        O -->|codex| Q[codex exec subprocess\nreads files via sandbox]
        O -->|deepagents| R[LLM orchestrator\n+ subagents]
        P & Q2 & Q & R --> S([ReviewResult])
    end

    S --> T

    subgraph P3["Phase 3 — Output"]
        T[format markdown] --> U[stdout / -o file]
        U -->|"--publish"| V{platform?}
        V -->|GITLAB_TOKEN| W[MR note +\ninline threads]
        V -->|GITHUB_TOKEN| X[PR comment +\nreview comments]
    end
```

### `--publish FILE` shortcut

When `--publish` receives a file path, the entire pipeline is skipped. Junior reads the .md file, wraps it in a `ReviewResult(pre_formatted=...)`, and publishes directly to the platform. Requires a platform token and CI variables — see [CI Setup](ci.md).

## Pipeline (text)

```
junior --prompts common
│
├─ Phase 1: COLLECT (deterministic, no AI)
│   ├─ git diff → parse changed files → commit messages
│   ├─ extra context: --context (text) AND --context-file (files)
│   └─ platform enrichment: GitLab/GitHub API → MR/PR metadata (if token set)
│
├─ Phase 2: REVIEW (AI)
│   ├─ load prompts from prompts/*.md
│   ├─ build user message (context_builder.py)
│   └─ dispatch to agent backend:
│       ├─ pydantic   → parallel sub-agents + summary agent
│       ├─ claudecode → claude -p subprocess (reads files via tools)
│       ├─ codex      → codex exec subprocess (reads files via sandbox)
│       └─ deepagents → LLM orchestrator + subagents
│
└─ Phase 3: OUTPUT
    ├─ always: format markdown → stdout or -o file
    └─ if --publish: also post to GitLab MR notes / GitHub PR comments
```

## Backend Dispatch Pattern

All three components (collect, agent, publish) are **interfaces** — each has multiple implementations that are interchangeable at runtime. The implementation is selected by enum value, which is a Python module path.

### Contracts

Each backend module must export one function with a fixed signature:

| Component | Function | Signature |
|-----------|----------|-----------|
| Collector | `collect()` | `(settings: Settings) -> CollectedContext` |
| Agent | `review()` | `(context: CollectedContext, settings: Settings, prompts: list[Prompt]) -> ReviewResult` |
| Publisher | `post_review()` | `(settings: Settings, result: ReviewResult) -> None` |

Implementations vary widely — subprocess calls (`claudecode`, `codex`), async SDK (`pydantic`), LLM orchestrator (`deepagents`) — but all conform to the same interface.

### Dispatch

```python
# config.py — enum value = module path
class AgentBackend(str, Enum):
    PYDANTIC = "junior.agent.pydantic"
    CLAUDECODE = "junior.agent.claudecode"
    CODEX = "junior.agent.codex"
    DEEPAGENTS = "junior.agent.deepagents"

# agent/__init__.py — dispatch
module = importlib.import_module(backend.value)
return module.review(context, settings, prompts)
```

New backend = one file + one enum member. See [Adding backends](adding_backends.md).

Short names work via `_missing_`: `AgentBackend("pydantic")` → `AgentBackend.PYDANTIC`.

## Platform Auto-Detection

Collector and publisher are auto-detected from token presence:

```
GITLAB_TOKEN set  → gitlab collector + gitlab publisher
GITHUB_TOKEN set  → github collector + github publisher
no token          → local collector  + local publisher
both tokens       → error (validation rejects at startup)
```

