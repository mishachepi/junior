"""ScriptRunbook — a manifest-driven runbook whose phases are shell commands.

Lets you build a runbook with **no Python**: a small YAML manifest points at a
system prompt and (optionally) a JSON-Schema plus two commands —

    collect:  command whose STDOUT becomes the user message the AI sees;
              omit it and the user message is read from Junior's STDIN instead
              (that's how `junior run | junior run` chains work)
    publish:  command that receives the AI's JSON output on STDIN

Junior turns the JSON-Schema into the harness's output schema, runs the harness
in between, and pipes the validated result to `publish`. The manifest is loaded
from `<project>/.junior/runbooks/` by the repo-local loader (opt-in), so it
follows the same trust model as a repo-local Python runbook.

Manifest (e.g. `.junior/runbooks/weather/weather.yaml`):

    name: weather
    description: what to wear today
    system_prompt: prompt.md           # path or inline text
    schema: weather.schema.json        # path (rel. to manifest) or inline mapping;
                                       # omit → DEFAULT_SCHEMA ({"result": "..."} )
    collect: ./collect.sh              # stdout = user message; omit → read STDIN
    publish: ./publish.sh              # stdin  = AI output JSON
    needs_git: false
    blocking: false

The minimal manifest is just a `system_prompt` — input from STDIN, output
`{"result": "..."}`. `collect`'s stdout is used verbatim (any text, not
necessarily JSON). `collect`/`publish` run with `cwd` = the manifest's
directory, inherit the environment plus `JUNIOR_PROJECT_DIR` and
`JUNIOR_CONTEXT_<KEY>` for every `--context KEY=VAL`, so a script can read the
user's extra context.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, create_model

from junior.config import Settings
from junior.runbook.base import Runbook, Usage
from junior.runbook.registry import register_runbook


class ScriptContext(BaseModel):
    """Whatever the `collect` command prints — used verbatim as the user message."""

    payload: str = ""


#: result shape when a manifest has no `schema` — one free-form text field, so
#: the minimal runbook is just a system prompt and chains still emit valid JSON.
DEFAULT_SCHEMA: dict = {
    "type": "object",
    "required": ["result"],
    "properties": {
        "result": {"type": "string", "description": "the produced text / answer"},
    },
}


# --- JSON-Schema → pydantic model (minimal, covers the common shapes) ---


def json_schema_to_model(name: str, schema: dict) -> type[BaseModel]:
    """Build a pydantic model from a JSON-Schema object (recursively)."""
    if schema.get("type") != "object" or "properties" not in schema:
        # Wrap a non-object schema so the harness still gets a structured model.
        return create_model(name, value=(_json_type(name, schema), ...))

    required = set(schema.get("required", []))
    fields: dict[str, tuple] = {}
    for fname, fschema in schema["properties"].items():
        typ = _json_type(f"{name}_{fname}", fschema)
        if fname in required:
            fields[fname] = (typ, ...)
        else:
            fields[fname] = (Optional[typ], None)
    return create_model(name, **fields)


def _json_type(name: str, schema: dict):
    t = schema.get("type")
    if t == "string":
        return str
    if t == "integer":
        return int
    if t == "number":
        return float
    if t == "boolean":
        return bool
    if t == "array":
        return list[_json_type(f"{name}_item", schema.get("items", {}))]
    if t == "object":
        return json_schema_to_model(name, schema)
    return str  # unknown / anyOf / missing → permissive string


# --- the parameterized runbook ---


class ScriptRunbook(Runbook[ScriptContext, BaseModel]):
    """Base for manifest runbooks. Concrete subclasses are built per manifest by
    `runbook_from_manifest` (which bakes in `_manifest` / `_base_dir`)."""

    context_model = ScriptContext
    _manifest: dict = {}
    _base_dir: Path = Path()
    _blocking: bool = False

    def collect(self, settings: Settings) -> ScriptContext:
        cmd = self._manifest.get("collect")
        if not cmd:
            # No collect command → the user message is the positional INPUT
            # argument if given, else whatever was piped into Junior itself
            # (the chaining mode: `junior run | junior run`).
            if settings.context.input_text:
                return ScriptContext(payload=settings.context.input_text)
            return ScriptContext(payload=_read_stdin())
        out = self._run(cmd, settings, capture=True)
        return ScriptContext(payload=out)

    def render(self, context: ScriptContext, settings: Settings, *, file_access: bool) -> str:
        return context.payload

    def system_prompt(self, settings: Settings) -> str:
        from junior.prompt_loader import load_prompts

        base = _read_maybe_file(self._manifest.get("system_prompt", ""), self._base_dir)
        extra = [p.body for p in load_prompts(list(settings.context.prompts)) if p.body.strip()]
        return "\n\n".join(p for p in (base, *extra) if p.strip())

    def publish(
        self,
        settings: Settings,
        result: BaseModel,
        usage: Usage,
        *,
        errors: list[str],
    ) -> None:
        # Runs only with --publish: feed the validated JSON to the publish command.
        # Without --publish the framework emits the same JSON via render_output.
        cmd = self._manifest.get("publish")
        payload = result.model_dump_json()
        if not cmd:
            from junior.cli.console import print_content

            print_content(payload)
            return
        self._run(cmd, settings, stdin=payload)

    def is_blocking(self, result: BaseModel) -> bool:
        return self._blocking

    def output_destination(self, settings: Settings, *, publish_enabled: bool) -> str:
        return f"script:{self.name}"

    # --- subprocess plumbing ---

    def _run(self, command: str, settings: Settings, *, capture: bool = False,
             stdin: str | None = None) -> str:
        env = dict(os.environ)
        env["JUNIOR_PROJECT_DIR"] = str(settings.context.project_dir)
        for key, value in settings.context.context.items():
            env[f"JUNIOR_CONTEXT_{key.upper()}"] = value
        proc = subprocess.run(
            command, shell=True, cwd=str(self._base_dir), env=env,
            input=stdin, text=True, capture_output=capture,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or "").strip()
            raise RuntimeError(
                f"script command failed (exit {proc.returncode}): {command}"
                + (f"\n{detail}" if detail else "")
            )
        return proc.stdout if capture else ""


def _read_stdin() -> str:
    """STDIN as the user message (when the manifest has no `collect`).

    On an interactive terminal (nothing piped) this returns "" instead of
    blocking — the prompt layer / `--context` may still carry the task."""
    import sys

    if sys.stdin is None or sys.stdin.isatty():
        return ""
    return sys.stdin.read()


def _read_maybe_file(value: str, base_dir: Path) -> str:
    """A manifest string is a file path if it resolves to a file, else inline text."""
    if not value:
        return ""
    candidate = base_dir / value
    if candidate.is_file():
        return candidate.read_text(encoding="utf-8")
    return value


def _load_schema(spec, base_dir: Path) -> dict:
    if isinstance(spec, dict):
        return spec
    return json.loads((base_dir / spec).read_text(encoding="utf-8"))


def runbook_from_manifest(manifest_path: Path) -> type[Runbook]:
    """Build + register a ScriptRunbook subclass from a YAML manifest."""
    import yaml

    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    base_dir = manifest_path.parent
    name = data.get("name") or base_dir.name or manifest_path.stem
    if not data.get("system_prompt") and not data.get("collect"):
        # everything else has a default; a manifest with neither is a typo
        raise ValueError(
            f"manifest '{manifest_path}' defines neither `system_prompt` nor `collect`"
        )

    schema = _load_schema(data["schema"], base_dir) if "schema" in data else DEFAULT_SCHEMA
    result_model = json_schema_to_model(f"{name}_output", schema)
    cls = type(
        f"Script_{name}",
        (ScriptRunbook,),
        {
            "name": name,
            "description": data.get("description", "script runbook (manifest)"),
            "result_model": result_model,
            "needs_git": bool(data.get("needs_git", False)),
            "_manifest": data,
            "_base_dir": base_dir,
            "_blocking": bool(data.get("blocking", False)),
        },
    )
    register_runbook(cls)
    return cls
