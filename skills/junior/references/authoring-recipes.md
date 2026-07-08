# Junior authoring recipes

Copy-paste starting points for writing your own runbooks and flows. Each is annotated
with a **live runbook from this repo** so the example is real, not invented. For the
exhaustive reference see `docs-site/src/content/docs/script_runbooks.md` and
`adding_runbooks.md`.

Golden rule: **do as much as possible in deterministic code (collect/publish); let the
LLM fill exactly one schema-shaped step.** The more you pin down, the more reproducible
the run.

---

## Recipe 1 — Minimal manifest: the three ways input arrives

The SKILL.md body shows the one-file minimal manifest (`system_prompt` only). The thing to
internalize here is **how a no-`collect` runbook gets its user message** — three sources,
in precedence order:

```yaml
# .junior/runbooks/summarize/summarize.yaml
system_prompt: |
  Summarize the input in three bullet points. Keep code identifiers verbatim.
```

```bash
junior run --runbook summarize "text to summarize"   # 1. positional argument (highest)
git log --oneline -20 | junior run --runbook summarize   # 2. piped stdin  ← how chains feed
junior run --runbook summarize                        # 3. interactive stdin, else empty
```

With no `schema` the output is the validated default `{"result": "<string>"}`; with no
`publish` that JSON goes to stdout — pipe-safe, which is exactly what makes Recipe 4 work.

---

## Recipe 2 — Full manifest with a real output schema (the `changelog` runbook)

This is the actual `.junior/runbooks/changelog/` runbook in this repo — a collect-only
runbook that drafts a Keep-a-Changelog section. Folder layout:

```
.junior/runbooks/changelog/
  changelog.yaml   # manifest
  collect.sh       # stdout → the user message
  prompt.md        # the instruction (system_prompt)
  schema.json      # AI output contract — auto-loaded (no `schema:` key needed)
```

**`changelog.yaml`** — note there is no `schema:` key; `schema.json` beside it is
auto-loaded:

```yaml
name: changelog
description: draft a Keep-a-Changelog "Unreleased" section from commits since the last tag
system_prompt: prompt.md
collect: ./collect.sh
needs_git: true
```

**`collect.sh`** — stdout is used verbatim as the user message; runs with `cwd` = the
manifest folder and gets `JUNIOR_PROJECT_DIR` in its environment:

```sh
#!/bin/sh
set -eu
cd "$JUNIOR_PROJECT_DIR"
last_tag=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
range="${last_tag:+$last_tag..HEAD}"; range="${range:-HEAD}"
echo "## Commits"; git log --no-merges --pretty=format:'- %h %s' "$range"
```

**`schema.json`** — plain JSON-Schema; `enum`s become closed sets, `description`s become
instructions to the model:

```json
{
  "type": "object",
  "required": ["entries"],
  "properties": {
    "entries": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["category", "text"],
        "properties": {
          "category": {"type": "string", "enum": ["Added","Changed","Fixed","Removed","Docs"]},
          "text": {"type": "string", "description": "one-line entry, imperative present tense"}
        }
      }
    }
  }
}
```

Run it: `junior run --runbook changelog`. Preview without an LLM call:
`junior dry-run --runbook changelog`.

---

## Recipe 3 — collect + publish, with `--context` (the `merger` merge-gate)

The real `.junior/runbooks/merger/` runbook: the LLM assesses a branch against a
checklist, and `publish.sh` acts on the verdict only with `--publish`.

**`merger.yaml`:**

```yaml
name: merger
description: "merge gate: assess a branch against the dev-flow checklist; --publish merges (ff-only) when ready"
system_prompt: prompt.md
collect: ./collect.sh
publish: ./publish.sh
needs_git: true
```

**`publish.sh`** — receives the **validated result JSON on stdin**, and reads a
`--context KEY=VAL` value via `JUNIOR_CONTEXT_<KEY>`:

```sh
#!/bin/sh
set -eu
JSON=$(cat)                                   # the gate's validated verdict
READY=$(printf '%s' "$JSON" | python3 -c 'import json,sys; print(str(json.load(sys.stdin)["ready"]).lower())')
BRANCH="${JUNIOR_CONTEXT_BRANCH:?pass --context branch=<name>}"
[ "$READY" = "true" ] && git -C "$JUNIOR_PROJECT_DIR" merge --ff-only "$BRANCH" || { echo "gate refused"; exit 1; }
```

Run it: `junior run --runbook merger --context branch=feat/x --publish`. Without
`--publish`, the verdict JSON just prints — nothing is merged.

---

## Recipe 4 — A flow (shell pipeline, per-link model)

Junior has **no flow object** — chain with the shell. Each no-`--publish` run prints one
JSON doc; each no-`collect` runbook reads stdin. Run the bulk step cheap, gate strong:

```bash
junior run --runbook draft   --harness pi        --model ollama:llama3 \
  | junior run --runbook refine --harness pydantic --model openai:gpt-4o-mini \
  | junior run --runbook gatekeeper --harness claudecode --publish
```

Make each downstream `system_prompt` state what arrives on stdin, e.g.:

```yaml
system_prompt: |
  STDIN carries JSON {"ready": bool, "notes": str} from a previous step.
  Verify the notes justify `ready`, tighten wording, and return the final decision.
```

Debug link-by-link:

```bash
junior dry-run --runbook refine        # exact prompt + user message, no LLM call
junior runs last | jq .output          # replay the previous link's output for free
```

---

## Recipe 5 — Python runbook (only when phases need real Python)

Reach for Python when collect/publish need an SDK, an API client, or typed models. The
smallest complete example in the repo is `src/junior/runbooks/weather/` (no git, no
platform, no API key).

```python
from pydantic import BaseModel, Field
from junior.config import Settings
from junior.runbook.base import Runbook, Usage
from junior.runbook.registry import register_runbook

class Ctx(BaseModel):
    topic: str

class Out(BaseModel):
    summary: str = Field(description="one-line summary")
    points: list[str] = Field(default_factory=list)

@register_runbook
class MyRunbook(Runbook[Ctx, Out]):
    name = "my_runbook"
    context_model = Ctx
    result_model = Out
    needs_git = False
    SYSTEM_PROMPT = "You are a concise analyst."

    def collect(self, settings: Settings) -> Ctx:
        return Ctx(topic="...")                       # keep heavy imports lazy, inside methods

    def render(self, context: Ctx, settings: Settings, *, file_access: bool) -> str:
        return f"Analyze: {context.topic}"            # file_access → skip inlining bulky content

    def publish(self, settings: Settings, result: Out, usage: Usage, *, errors: list[str]) -> None:
        print(result.model_dump_json(indent=2))       # runs ONLY with --publish
```

Ship it one of four ways: repo-local (`.junior/runbooks/my_runbook/my_runbook.py`),
built-in (`src/junior/runbooks/<pkg>/` + import in `__init__.py`), pip entry-point
(`junior.runbooks` group), or direct path (`--runbook "pkg.module:MyRunbook"`).

---

## Authoring checklist

- [ ] Manifest has at least `system_prompt` **or** `collect`.
- [ ] Output contract in `schema.json` (or `schema:`), else the `{"result": "<string>"}`
      default applies — fine for free text, not for anything a downstream step parses.
- [ ] `collect` prints the user message to **stdout**; `publish` reads result JSON from
      **stdin**; both may use `JUNIOR_PROJECT_DIR` and `JUNIOR_CONTEXT_<KEY>`.
- [ ] A non-zero exit from `collect`/`publish` aborts the run — fail loudly on bad input.
- [ ] `needs_git: true` only if the runbook diffs/queries a git repo.
- [ ] For chains: downstream `system_prompt` describes the stdin JSON; test each link with
      `dry-run` before wiring the pipe.
- [ ] Repo-local runbooks execute repo code — same trust as a Makefile. Untrusted repo →
      `local_runbooks: false`.

## Common gotchas

- **`junior run` exits 2 with no runbook** — selection is explicit; pass `--runbook`, set
  `runbook:` in `.junior.yaml`, or `RUNBOOK` env. No implicit default.
- **`--publish` vs default** — without `--publish` the custom `publish` never runs; the raw
  JSON is printed (pipe-safe). Side effects live only in `publish`.
- **Prompt bleed across runbooks** — put review/task rules under `runbooks.<name>.prompts`
  (scoped), not `context.prompts` (global), so unrelated runbooks don't inherit them (and
  their token cost). See this repo's `.junior.yaml`.
- **`schema.json` not applied** — it must sit in the same folder as the manifest; an
  explicit `schema:` key overrides it.
