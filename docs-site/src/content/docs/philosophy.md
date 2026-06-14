---
title: "Philosophy"
---

# Philosophy — why Junior exists, and why it's called that

Junior is a **universal wrapper around an LLM, kept as deterministic as possible**.
Everything that *can* be code — gathering context, shaping it, posting the result —
*is* code. The model is invoked for exactly one step: turning a well-formed input
into a schema-constrained output. Nothing more is delegated to it than has to be.

## The shape of the idea

Most of an "AI agent" is not the AI. It's the plumbing around it: deciding what
to look at, assembling that into a prompt, validating the answer, and doing
something with it. Junior treats that plumbing as the product and the LLM as a
single, replaceable component inside it.

```
  you write these (deterministic)          this is the only AI step
  ────────────────────────────────         ────────────────────────
  collect  →  render  →  [ system + user message ]  →  HARNESS  →  output (your schema)  →  publish
  └──────────────── a Runbook you control ───────────────┘     └─ swappable ─┘   └─ you control ─┘
```

- **You invent the modules.** A runbook is just *collect context → hand it to an
  LLM → take a correctly-shaped result → publish it however you like*. Code review
  of a git diff is the built-in example, but the same frame fits reviewing a Jira
  ticket, summarising a Confluence page, or auditing a config file. You write the
  collection and publication; nothing about the framework assumes "diff" or "PR".
- **The harness just fills in the schema.** Each runbook declares the output
  schema it needs. The harness (`claudecode`, `codex`, `pydantic`, `deepagents`,
  `pi`) is schema-agnostic — it takes that schema as a parameter and returns an
  instance of it. The name is deliberate: these are wrappers around agentic CLIs and SDKs,
  so Junior *harnesses* a model rather than being the inference engine. Swap
  harnesses freely; the deterministic parts on either side don't change.
- **Determinism as much as possible.** The non-deterministic surface is squeezed
  down to one call with a fixed input and a validated, typed output. Everything
  around it is ordinary, testable, reviewable code. That's what makes a run
  reproducible enough to trust in CI.

> [!NOTE]
> This is why the extension points are **Runbook** and **Harness** and nothing else — see
> the [Glossary](glossary.md) for each entity, and [Architecture](architecture.md)
> for how they fit together.

## Why "Junior"

Because **the responsibility stays with the human.** A junior engineer does real
work, but a senior signs off — the senior owns the outcome. The AI here is a tool
in exactly that sense: useful, fast, occasionally wrong, and never accountable.

When you delegate a task to this runbook, you are delegating it the way you'd
delegate to a junior: you remain responsible for what gets shipped. Junior can
read a diff and flag what looks risky, but it does not *decide* — it advises. The
review you post, the change you merge, the bug you miss: those are yours, just as
they would be if a junior on your team had drafted them and you'd approved them.

> [!IMPORTANT]
> Treat Junior's output as a junior colleague's draft, not a verdict. The model is
> the instrument; the engineer is the author. Read [Prompt injection &
> security](prompt_injection.md) for why this matters in practice — an LLM reading
> untrusted code can be steered, and only a human in the loop catches that.

## What follows from this

- **No magic.** Runbook and harness are selected explicitly (flags / config / env),
  never auto-detected from the environment. You always know what ran.
- **Every run leaves a trace.** Because the responsibility is yours, Junior
  records what it did: each run writes `<project_dir>/.junior/output/{timestamp}.json`
  — runbook, harness, inputs digest, and the full structured output. The
  accountable party can always replay exactly what was delegated and what came
  back. On by default; opt out with `--no-record`.
- **Config files are the source of truth.** Flags and env vars are sugar and
  safety (secrets stay in env), not the canonical record of how a run is shaped.
- **Forkable on purpose.** The core abstractions are ABCs so that someone forking
  Junior implements a clear contract and fails loudly if they miss a method —
  rather than discovering a silent gap at runtime. Adding a runbook or a harness
  is implementing one interface, not patching the core. See
  [Adding runbooks & harnesses](adding_backends.md).
