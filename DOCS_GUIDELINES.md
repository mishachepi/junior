# Documentation guidelines

Rules for writing and editing Junior's docs (`docs-site/src/content/docs/`), distilled
from the 0.2.0 documentation pass. Mechanical conventions (frontmatter, link rewriting,
callouts) live in `docs-site/README.md`; what to update when code changes is the table
in `CLAUDE.md`. This file is about *how to write*.

## Principles

1. **Simplify first.** Every edit should make the page shorter or clearer, ideally both.
   If a section can be a sentence, make it a sentence. If a sentence can go, cut it.
2. **Only verifiable claims.** Document behavior you can point to in the code. No
   invented asides, no marketing claims that "sound right" (a flagged example:
   "no prompt needed — every runbook ships a default" — false; `--prompt` *appends* to
   the runbook's base prompt). When unsure, read the source before writing.
3. **One fact, one page.** Each topic has a home; other pages link to it instead of
   restating it. Homes: exit codes → `cli.md`, publish-vs-raw → `cli.md`, harness
   comparison → `agent_backends.md`, settings/env/priority → `configuration.md`,
   prompt mechanics → `prompts.md`, security model → `prompt_injection.md`.
   Duplicated tables rot — the per-harness table that lived in `prompts.md` had
   already lost `pi` and referenced a removed mode when it was cut.
4. **Plain language, no invented jargon.** The term "axes" is banned — say
   "Runbook and Harness are independent", "two extension points", "no separate
   platform selector". Prefer words the reader already knows.
5. **Universal tool, code review as flagship.** Don't write as if Junior is a code
   reviewer with extras. Code review is the built-in flagship; the framework assumes
   nothing about code. Frame examples accordingly.
6. **Selling but honest.** Lead with the benefit, follow with a ready-to-run command.
   Use-case writing pattern: 2–3 lines of benefit + one copy-pasteable command/manifest.
7. **Simple pages up front, depth in Architecture.** Top-level pages (About, Getting
   started, Guides) stay short and practical; internals (per-harness mechanics,
   framework contracts, walkthroughs) live under the collapsed Architecture group.
8. **Don't teach other products.** Link to third-party install docs (Claude Code,
   codex, pi) instead of embedding their install commands; they go stale.

## Terminology

- **runbook** — the task unit (collect → one LLM call → publish). Not "playbook",
  not "pipeline".
- **harness** — the LLM driver. Always the five names: `claudecode`, `codex`,
  `pydantic`, `deepagents`, `pi`. Any enumeration that forgets `pi` (or
  `bitbucket_pr_review` among runbooks) is a bug — check every list you touch.
- **`--runbook` / `--harness`** are *primary selectors* (what this invocation runs);
  the other scalar flags are *aliases for `--env KEY=VALUE`*. Keep that distinction
  in help texts and flag tables.
- **publish contract**, phrase it exactly: without `--publish` → raw result JSON on
  stdout/`-o` (pipe-safe, logs on stderr); with `--publish` → the runbook's custom
  publish, raw output not printed.
- "Deterministic as much as possible" is the core pitch — keep the phrase intact.

## Style

- Short sentences. Tables only for enumerable facts; explanation goes in prose.
- Every command shown must actually work as written — test it before committing.
- Cross-link with relative `*.md` paths in `.md` files (the remark plugin rewrites
  them); route-style `/page/` links in `.mdx`.
- A new/renamed page needs a `starlight.sidebar` entry in `docs-site/astro.config.mjs`.
- After any docs change: `cd docs-site && npm run build` must pass; check the page
  on the preview server before committing.
