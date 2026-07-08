---
name: junior
description: This skill should be used when the user asks "how does Junior work", to "write a Junior runbook", "create a runbook", "add a runbook manifest", "make a .junior/runbooks entry", "chain runbooks", "build a Junior flow/pipeline", "add a harness", "run junior", or works with `junior run` / `.junior/` / `schema.json` in this repo. Explains Junior's mental model and how to author your own runbooks and flows — not limited to code review.
version: 0.1.0
---

# Junior — how it works, and how to author runbooks & flows

Junior is a **universal wrapper around an LLM, kept as deterministic as possible**.
Everything that *can* be code — gathering context, shaping it, posting the result — *is*
code. The model is invoked for exactly one step: turning a well-formed input into a
schema-constrained output. Code review of a git diff is the flagship runbook, **not** the
boundary — the same frame fits a Jira ticket, a config file, a deploy log, anything.

```
  ┌────── a Runbook you control (deterministic) ──────┐
     collect   →     one LLM call    →    publish
                    └─ Harness ─┘
                     (swappable)
```

## The two concepts (there are only two)

- **Runbook** — one *task domain*. Owns its **context schema** (input) and **result
  schema** (output) plus the logic: `collect → render → system_prompt → publish`. Chosen
  explicitly (`--runbook NAME`); there is no auto-detection and no implicit default.
- **Harness** — one *LLM driver* (`claudecode`, `codex`, `pi`, `pydantic`, `deepagents`).
  **Schema-agnostic**: `complete(*, system_prompt, user_message, output_schema, settings)`
  takes the output schema as a *parameter*, so one set of harnesses serves every runbook.

The senior/junior split is the point: **you** spell out the deterministic recipe; the LLM
fills the single non-deterministic step and **advises, never decides**. Responsibility for
what ships stays with the human. Every run writes an audit record to
`.junior/output/{timestamp}.json` (runbook, harness, inputs digest, full output) unless
`--no-record`.

Canonical background: `docs-site/src/content/docs/philosophy.md`,
`architecture.md`, `glossary.md`.

## Authoring a runbook — pick the lighter path first

### Path A — YAML manifest (no Python; any language)

The fastest way to "make your own runbook". Drop a folder under `.junior/runbooks/`; each
phase is an ordinary shell command. **Minimal** runbook = one file with just a prompt:

```yaml
# .junior/runbooks/summarize/summarize.yaml
system_prompt: |
  Summarize the input in three bullet points. Keep code identifiers verbatim.
```
```bash
git log --oneline -20 | junior run --runbook summarize
```

Everything unspecified has a default: no `collect` → user message is the positional arg or
**stdin**; no `schema` → a `schema.json` beside the manifest is auto-loaded, else
`{"result": "<string>"}`; no `publish` → the validated result JSON prints to stdout/`-o`.

**Full manifest keys** (a manifest needs at least `system_prompt` *or* `collect`):

| Key | Meaning |
|-----|---------|
| `name` | registry name (default: folder name) |
| `description` | one-line summary for `junior list` |
| `system_prompt` | path (rel. to manifest) or inline text — the instruction |
| `schema` | JSON-Schema for the AI result, path or inline. Omit → `schema.json` auto-load → default |
| `collect` | command whose **stdout = the user message** (verbatim; need not be JSON). Omit → read stdin |
| `publish` | command that gets the **validated result JSON on stdin**. Runs only with `--publish`; omit → JSON printed |
| `needs_git` | `true` = preflight requires a `.git` dir |
| `blocking` | `true` = exit code 1 on every result (fail CI) |

Both commands run with `cwd` = the manifest folder and inherit the environment plus
`JUNIOR_PROJECT_DIR` and one `JUNIOR_CONTEXT_<KEY>` per `--context KEY=VAL`. A non-zero
exit aborts the run with that command's stderr.

Two live examples ship in *this* repo — read them as templates:
`.junior/runbooks/changelog/` (collect-only, drafts a changelog) and
`.junior/runbooks/merger/` (collect + publish merge-gate). Full reference:
`docs-site/src/content/docs/script_runbooks.md`. Copy-paste example:
`docs-site/src/content/docs/examples/runbooks/weather/`.

### Path B — Python subclass (when phases aren't just shell)

Subclass `Runbook[CtxModel, ResultModel]` and register it. Use this when collect/publish
need real Python (an SDK, an API client, typed models):

```python
from junior.runbook.base import Runbook, Usage
from junior.runbook.registry import register_runbook

@register_runbook
class JiraReview(Runbook[JiraContext, JiraFindings]):
    name = "jira_review"
    context_model = JiraContext      # input schema (JSON round-trip for --from-file)
    result_model = JiraFindings      # output schema handed to the harness
    SYSTEM_PROMPT = "You are a Jira reviewer."
    def collect(self, settings): ...              # keep heavy imports lazy
    def render(self, context, settings, *, file_access): ...   # build the user message
    def publish(self, settings, result, usage, *, errors): ... # only with --publish
```

Required: `name`, `context_model`, `result_model`, `collect`, `render`, `publish`.
`file_access` tells whether the chosen harness reads files itself, so bulky content need
not be inlined. The smallest end-to-end non-code-review example is
`src/junior/runbooks/weather/`. Reference: `docs-site/src/content/docs/adding_runbooks.md`.

**Four ways to ship a runbook:** built-in (`src/junior/runbooks/<pkg>/`), pip entry-point
(`junior.runbooks` group), direct path (`--runbook "pkg.module:ClassName"`), or repo-local
(`.junior/runbooks/`, on by default via `local_runbooks`). Repo-local runs code/commands
shipped in the repo — **same trust model as a Makefile**; set `local_runbooks: false` for
untrusted repos (`docs-site/src/content/docs/prompt_injection.md`).

## Flows — chaining runbooks (a shell pipeline, not a config format)

Junior has **no flow object on purpose** — orchestration stays in your shell / Makefile /
CI, so each link remains a deterministic single step with its own audit record. Two rules
make chaining work: (1) without `--publish`, each `junior run` prints **exactly one JSON
doc** matching its schema; (2) a runbook **without `collect` reads its user message from
stdin**. Compose them:

```bash
junior run --runbook ansible_report \
  | junior run --runbook comment_review \
  | junior run --runbook comment_gatekeeper --publish
```

`--harness`/`--model` are **per invocation**, so run the bulk step on a cheap/local model
and the final gate on a strong one:

```bash
junior run --runbook draft --harness pi --model ollama:llama3 \
  | junior run --runbook gatekeeper --harness claudecode --publish
```

Make the downstream runbook's `system_prompt` state what arrives on stdin (e.g. *"STDIN
carries JSON `{status, comment}` from a previous step"*). Debug link-by-link with
`junior dry-run --runbook X` (shows the exact prompt + user message, no LLM call) and
`junior runs last | jq .output` (replay the prior link's output for free). Recipe:
`docs-site/src/content/docs/script_runbooks.md` → "Chaining Juniors into a pipeline".

## CLI essentials

| Command | Purpose |
|---------|---------|
| `junior run --runbook NAME` | collect → LLM → (publish or print JSON) |
| `junior dry-run --runbook NAME` | show the exact system prompt + user message; **no** LLM call |
| `junior list` / `junior config list` | registered runbooks + harnesses (+ readiness) |
| `junior config show` / `config env` | effective config / required env vars |
| `junior runs [last]` | browse run records under `.junior/output/` |

Key flags: `--runbook`, `--harness`, `--model`, `--publish` (run custom publish),
`-o FILE` (write raw output), `--from-file ctx.json` (skip `collect`),
`--context KEY=VAL` (pass to manifest scripts), `--prompt` / `--prompt-file` (append to
the system prompt), `--no-record`. Config precedence: CLI flag → `.junior.yaml` (repo) →
`~/.config/junior/settings.yaml` → env. **Prompts are scoped per runbook** under
`runbooks.<name>.prompts` so unrelated runbooks don't inherit another's instructions (see
this repo's `.junior.yaml`). Full CLI: `docs-site/src/content/docs/cli.md`.

## Harnesses at a glance

`claudecode` (default, core, reads files) · `pi` (core, reads files, incl. local models via
Ollama/LM Studio/vLLM) · `codex` (`junior[codex]`, reads files) · `pydantic`
(`junior[pydantic]`, diff inlined, API key required) · `deepagents` (deprecated — use
`pydantic`). `file_access=True` harnesses explore the repo themselves; `False` ones only
see the message. Details: `docs-site/src/content/docs/agent_backends.md`.

## Additional resources

- **`references/authoring-recipes.md`** — copy-paste recipes: minimal manifest, full
  manifest with `schema.json`, a 3-step flow, and a Python runbook stub, annotated with
  the repo's own live runbooks as worked examples.
- **Canonical docs** (`docs-site/src/content/docs/`) — the single source of truth; this
  skill distills and routes to them: `philosophy.md`, `architecture.md`, `glossary.md`,
  `script_runbooks.md`, `adding_runbooks.md`, `adding_harnesses.md`, `cli.md`,
  `configuration.md`, `prompt_injection.md`.
