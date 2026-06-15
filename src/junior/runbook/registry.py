"""Lookup for runbooks (by name) and harnesses (by HarnessKind enum).

Runbooks come from four sources, all merged into one registry:

1. **Built-in** — every subpackage of `junior.runbooks` exposing a `runbook`
   module; auto-discovered (no hardcoded list).
2. **External plugins** — third-party packages declaring a `junior.runbooks`
   entry point; installed with pip, no fork needed:

       [project.entry-points."junior.runbooks"]
       jira_review = "junior_jira.runbook:JiraReview"

3. **Direct path** — `--runbook "pkg.module:ClassName"` (or the same in config)
   loads a Runbook subclass directly, an escape hatch for quick experiments.
4. **Repo-local** — `<project>/.junior/runbooks/` (Python class or YAML manifest),
   loaded by `load_local_runbooks()`; opt-in via `settings.local_runbooks` since
   it executes code shipped in the reviewed repository.

Harnesses are resolved lazily via the `HarnessKind` enum, whose value is the
harness module path; each such module exposes a module-level `HARNESS` instance.
"""

from __future__ import annotations

import importlib
import importlib.util
import pkgutil
import sys
from importlib.metadata import entry_points
from pathlib import Path

import structlog

from junior.config import HarnessKind
from junior.runbook.base import Harness, Runbook

logger = structlog.get_logger()

ENTRY_POINT_GROUP = "junior.runbooks"

_RUNBOOKS: dict[str, type[Runbook]] = {}
_discovered = False


def register_runbook(cls: type[Runbook]) -> type[Runbook]:
    """Class decorator: register a Runbook subclass under its `name`."""
    _RUNBOOKS[cls.name] = cls
    return cls


def _discover() -> None:
    """Populate the registry from built-in subpackages + entry-point plugins."""
    global _discovered
    if _discovered:
        return
    _discovered = True

    import junior.runbooks as root

    for info in pkgutil.iter_modules(root.__path__):
        if not info.ispkg:
            continue
        try:
            # Importing the package runs its __init__, which registers the
            # runbook(s) it defines. Deps stay lazy (inside collect/publish).
            importlib.import_module(f"junior.runbooks.{info.name}")
        except Exception as e:  # missing dep or bad package — skip, don't crash
            logger.warning("failed to load built-in runbook", package=info.name, error=str(e))

    for ep in entry_points(group=ENTRY_POINT_GROUP):
        try:
            cls = ep.load()
        except Exception as e:
            logger.warning("failed to load runbook plugin", entry_point=ep.name, error=str(e))
            continue
        if isinstance(cls, type) and issubclass(cls, Runbook):
            register_runbook(cls)
        else:
            logger.warning("runbook plugin is not a Runbook subclass", entry_point=ep.name)


_local_loaded_dirs: set[str] = set()


def load_local_runbooks(project_dir) -> list[str]:
    """Import repo-local runbooks from ``<project_dir>/.junior/runbooks/`` (opt-in).

    Layout (either works):
      .junior/runbooks/weather/weather.py   ← folder per runbook (preferred)
      .junior/runbooks/quick.py             ← single-file runbook

    Each must expose a ``@register_runbook`` class. The runbooks root is put on
    ``sys.path`` (and kept there) so a runbook can split across sibling modules
    and lazy-import them at runtime. SECURITY: this executes code shipped in the
    repo — callers gate it behind ``settings.local_runbooks``.

    Returns the names newly registered. Idempotent within a process.
    """
    base = Path(project_dir) / ".junior" / "runbooks"
    key = str(base.resolve())
    if key in _local_loaded_dirs:
        return []
    if not base.is_dir():
        return []
    _local_loaded_dirs.add(key)
    _discover()  # built-ins first, so name clashes are visible

    if str(base) not in sys.path:
        sys.path.insert(0, str(base))  # left on path: runbooks may lazy-import siblings

    loaded: list[str] = []
    for entry in sorted(base.iterdir()):
        if entry.name.startswith((".", "_")):
            continue
        if entry.is_dir():
            manifest = _find_manifest(entry)
            if manifest is not None:
                loaded += _load_manifest(manifest)
            else:
                loaded += _import_local(
                    (entry.name, f"{entry.name}.{entry.name}", f"{entry.name}.runbook"), entry
                )
        elif entry.suffix == ".py":
            loaded += _import_local((entry.stem,), entry)
        elif entry.suffix in (".yaml", ".yml"):
            loaded += _load_manifest(entry)
    return loaded


def _find_manifest(folder: Path) -> Path | None:
    """A folder runbook's YAML manifest: `<name>.yaml`, `manifest.yaml`, … (if any)."""
    for stem in (folder.name, "manifest", "runbook"):
        for ext in (".yaml", ".yml"):
            candidate = folder / f"{stem}{ext}"
            if candidate.is_file():
                return candidate
    return None


def _load_manifest(path: Path) -> list[str]:
    """Build a ScriptRunbook from a manifest; return the names it registered."""
    from junior.runbooks.script import runbook_from_manifest

    before = set(_RUNBOOKS)
    try:
        runbook_from_manifest(path)
    except Exception as e:
        logger.warning("failed to load script runbook", path=str(path), error=str(e))
        return []
    return [n for n in _RUNBOOKS if n not in before]


def _import_local(module_names: tuple[str, ...], entry: Path) -> list[str]:
    """Try each candidate module; return runbook names the first importable one adds."""
    for mod in module_names:
        before = set(_RUNBOOKS)
        try:
            importlib.import_module(mod)
        except ModuleNotFoundError:
            continue  # try the next naming convention
        except Exception as e:
            logger.warning("failed to load local runbook", path=str(entry), error=str(e))
            return []
        new = [n for n in _RUNBOOKS if n not in before]
        if new:
            return new
    return []


def _load_from_path(spec: str) -> Runbook:
    """Load a runbook from a `module:ClassName` spec."""
    module_path, _, class_name = spec.partition(":")
    if not module_path or not class_name:
        raise ValueError(f"runbook path must be 'module:ClassName', got '{spec}'")
    try:
        cls = getattr(importlib.import_module(module_path), class_name)
    except (ImportError, AttributeError) as e:
        raise ValueError(f"cannot load runbook '{spec}': {e}") from e
    if not (isinstance(cls, type) and issubclass(cls, Runbook)):
        raise ValueError(f"'{spec}' is not a Runbook subclass")
    return cls()


def get_runbook(name: str) -> Runbook:
    """Instantiate a runbook by registry name, or by `module:ClassName` path."""
    if ":" in name:
        return _load_from_path(name)
    _discover()
    try:
        return _RUNBOOKS[name]()
    except KeyError:
        known = ", ".join(sorted(_RUNBOOKS)) or "(none)"
        raise ValueError(f"unknown runbook '{name}'. Known: {known}") from None


def available_runbooks() -> list[str]:
    """All registered runbook names (built-ins + plugins). Used by `junior init`."""
    _discover()
    return sorted(_RUNBOOKS)


def available_runbooks_meta() -> list[tuple[str, str]]:
    """(name, description) for every registered runbook, sorted by name."""
    _discover()
    return [(name, getattr(cls, "description", "")) for name, cls in sorted(_RUNBOOKS.items())]


# Static harness metadata for `junior list` — (description, pip extra, probe
# module). Deliberately import-free: the point of listing harnesses is to show
# ones whose extra ISN'T installed yet, so we can't read ClassVars off a module
# that may fail to import. The pip extra usually equals the short name ("" =
# ships in the core install). The probe is the third-party package the extra
# pulls — checked with `find_spec` (locates without executing, so listing never
# triggers a heavy import like LangChain); "" means nothing to probe (core).
HARNESS_META: dict[HarnessKind, tuple[str, str, str]] = {
    HarnessKind.CLAUDECODE: ("claude CLI subprocess (no API key)", "", ""),
    HarnessKind.CODEX: ("codex CLI subprocess", "codex", "openai"),
    HarnessKind.PYDANTIC: ("single structured call via pydantic-ai", "pydantic", "pydantic_ai"),
    HarnessKind.DEEPAGENTS: (
        "LangChain orchestrator — DEPRECATED (unreliable; use pydantic)",
        "deepagents",
        "deepagents",
    ),
    HarnessKind.PI: ("pi CLI subprocess — incl. local models (models.json)", "", ""),
}


def harness_available(kind: HarnessKind) -> bool:
    """True if the harness's extra is installed — without importing it.

    Uses `find_spec` on the harness's probe package, which only *locates* the
    module (no execution), so calling this for every harness can't hang on a
    slow top-level import.
    """
    _, _, probe = HARNESS_META[kind]
    if not probe:
        return True  # core harness, no extra to install
    try:
        return importlib.util.find_spec(probe) is not None
    except (ImportError, ValueError):
        return False


def get_harness(kind: HarnessKind) -> Harness:
    """Resolve the LLM harness for a HarnessKind enum (value = module path)."""
    module = importlib.import_module(kind.value)
    harness = getattr(module, "HARNESS", None)
    if not isinstance(harness, Harness):
        raise RuntimeError(
            f"harness module '{kind.value}' does not expose a HARNESS instance"
        )
    return harness
