---
title: "Adding a Harness"
---

# Adding a Harness

A **harness** is one way to call an LLM — a schema-agnostic driver that takes the output
schema as a parameter, so a single set of harnesses serves *every* runbook. It's one of
Junior's two extension interfaces; the other is the [Runbook](adding_runbooks.md). Both
are ABCs in `src/junior/runbook/base.py`.

```
Harness (driver)
----------------
complete(*, system_prompt, user_message, output_schema, settings) -> LLMResult
file_access: ClassVar[bool]
```

> [!NOTE]
> `Harness` is an ABC **on purpose**. This is a forkable framework: a forgotten method
> should fail loudly at instantiation, not slip past a type checker.

Add a harness to support a new model provider, SDK, or CLI. The whole job is
**implementing one interface** (`Harness`, two methods — one of them optional) plus two
one-line registrations; the cross-harness contract tests pick the new harness up
automatically.

> [!TIP]
> A complete, real worked example is the `pi` harness
> (`src/junior/harnesses/pi.py`, ~200 lines): a subprocess CLI driver with no native
> structured-output mode, so it also shows the prompt-embedded-schema pattern and a
> tolerant JSON parser. It was written exactly by following the steps below.

## Step 1: Create the module

```
src/junior/harnesses/my_harness.py
```

Expose a module-level `HARNESS` instance implementing `Harness`:

```python
"""My custom LLM harness."""

import structlog
from pydantic import BaseModel

from junior.config import Settings
from junior.runbook.base import Harness, LLMResult, Usage

logger = structlog.get_logger()


class MyHarness(Harness):
    name = "my_harness"         # matches the HarnessKind member
    file_access = False         # True if the harness reads repo files itself
    config_fields = ("model",)  # LLMSettings fields you honor (for `config show`)
    env_vars = ()               # EnvVar tuples you need (for `config env`)
    setup_note = ""             # one-line setup hint shown by `config env`

    def is_ready(self) -> str | None:
        # Optional env/CLI self-check shown by `junior list` (e.g. "ready" /
        # "not ready: `mycli` not found"). Keep it cheap — no SDK imports.
        return None

    def complete(
        self,
        *,
        system_prompt: str,
        user_message: str,
        output_schema: type[BaseModel],
        settings: Settings,
    ) -> LLMResult:
        # Call the model however you like. Return an LLMResult whose `.output`
        # is a *validated instance of output_schema* (not the schema class).
        output = output_schema(...)  # parse/validate the model's response
        return LLMResult(
            output=output,
            usage=Usage(input_tokens=0, output_tokens=0, total_tokens=0),
            errors=[],  # partial-failure notes the runbook can surface
        )


HARNESS = MyHarness()  # the registry looks up this exact attribute name
```

Key points:

- `complete()` is **schema-agnostic**. `output_schema` is a parameter — return
  `LLMResult.output` as a validated instance of it. The same harness serves every
  runbook.
- Set `file_access = True` if the harness reads repository files itself (like
  `claudecode` / `codex`). Runbooks check this in `render()` to decide whether to
  inline a full diff (file-access harnesses don't need it).
- Populate `Usage` for token accounting; the runner threads it through to publish.
- Put partial-failure notes in `LLMResult.errors` — runbooks can surface them.
- **Lazy-import any heavy SDK inside `complete()`**, not at module top level — the
  registry imports every harness module for `junior list` / `config show`, and that
  must stay cheap (see `pydantic.py` / `deepagents.py`).
- If the engine has no native structured-output mode, embed the schema in the system
  prompt and validate the reply yourself — `pi.py` shows the pattern
  (`_OUTPUT_CONTRACT` + `_parse_response`).

## Step 2: Add the enum member

The `HarnessKind` enum value is the harness's module path; the registry resolves it via
`importlib.import_module(...).HARNESS`:

```python
# config.py
class HarnessKind(_ModulePathEnum):
    PYDANTIC = "junior.harnesses.pydantic"
    CODEX = "junior.harnesses.codex"
    CLAUDECODE = "junior.harnesses.claudecode"
    DEEPAGENTS = "junior.harnesses.deepagents"
    PI = "junior.harnesses.pi"
    MY_HARNESS = "junior.harnesses.my_harness"   # <-- add
```

## Step 3: Register for `junior list`

Add one `HARNESS_META` entry in `runbook/registry.py` — a description, the pip extra
name, and a "probe" package checked with `find_spec` (so listing never imports a heavy
SDK). A pure-subprocess harness has nothing to probe:

```python
HARNESS_META[HarnessKind.MY_HARNESS] = ("one-line description", "my_harness", "some_sdk")
# subprocess-only (no Python extra):     ("one-line description", "", "")
```

## Step 4: Update validation (if needed)

If your harness manages its own auth (like the CLI-driven `codex` / `claudecode` / `pi`),
add it to the skip list in `Settings._validate_review()` so it isn't forced to provide
an API key:

```python
if harness in (HarnessKind.CODEX, HarnessKind.CLAUDECODE, HarnessKind.PI,
               HarnessKind.MY_HARNESS):
    return []
```

## Step 5: Add a dependency extra (if needed)

```toml
# pyproject.toml
[project.optional-dependencies]
my_harness = ["some-sdk>=1.0"]
```

Done. `--harness my_harness` (or `HARNESS=my_harness`) now drives any runbook — and the
cross-harness contract tests (`tests/test_harnesses.py`) cover the new member
automatically because they parametrize over `HarnessKind`. Add a deep test file
(mocked subprocess / SDK) per the existing `tests/test_pi_harness.py` pattern.

## Removing a harness

Delete `src/junior/harnesses/<name>.py`, remove its `HarnessKind` member, drop it from
any validation skip list in `config.py`, and remove its `pyproject.toml` extra. Dispatch
is fully decoupled — no other files reference harnesses by hand.

## Checklist

- [ ] `src/junior/harnesses/<name>.py` with a module-level `HARNESS` instance
- [ ] `complete()` returns `LLMResult` whose `.output` is a validated `output_schema`
- [ ] `file_access` set correctly (`True` if it reads repo files itself)
- [ ] `HarnessKind` member added in `config.py`
- [ ] Validation skip list updated (if it manages its own auth)
- [ ] `pyproject.toml` extra added (if it has deps)
- [ ] Tested: `junior run --harness <name>`
