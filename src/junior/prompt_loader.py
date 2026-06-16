"""Load review prompts.

Junior is a thin wrapper — it doesn't ship its own prompts. The user supplies
each prompt as either inline text or a `file://...` URI pointing at a `.md`
file. Both shapes flow through `context.prompts` (one list).

Examples live in `docs-site/src/content/docs/examples/prompts/` (not loaded automatically).
"""

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

import structlog
import yaml

logger = structlog.get_logger()


@dataclass
class Prompt:
    name: str
    description: str
    body: str
    source_path: str


def load_prompts(entries: list[str]) -> list[Prompt]:
    """Resolve a list of prompt entries into Prompt objects.

    Each entry is either:
      - a `file://...` URI → read the file and parse frontmatter, OR
      - any other string → treat as inline prompt text.

    Empty inline entries are skipped (config layers can produce them).
    """
    result: list[Prompt] = []
    inline_idx = 0
    for entry in entries:
        if entry.startswith("file://"):
            result.append(_load_prompt_uri(entry))
        else:
            body = entry.strip()
            if not body:
                continue
            inline_idx += 1
            result.append(
                Prompt(
                    name=f"inline_{inline_idx}",
                    description="",
                    body=body,
                    source_path="<cli>",
                )
            )
    if result:
        logger.debug(
            "prompts loaded",
            names=[p.name for p in result],
            total_body_size=sum(len(p.body) for p in result),
        )
    return result


def merge_prompts(base: str, entries: list[str]) -> str:
    """Append prompt-entry bodies onto a base string, blank-line separated.

    The one composition helper for a runbook's system prompt: its `SYSTEM_PROMPT`
    role plus the user's `context.prompts` (`--prompt` / `--prompt-file`). Each
    entry is inline text or a `file://...` URI; blank parts are dropped.
    """
    bodies = [p.body for p in load_prompts(entries)]
    return "\n\n".join(s.strip() for s in (base, *bodies) if s.strip())


def _load_prompt_uri(uri: str) -> Prompt:
    """Read a `file://...` prompt. The URI must be absolute (resolved upstream)."""
    parsed = urlparse(uri)
    raw = unquote(parsed.path)
    if parsed.netloc and parsed.netloc not in ("", "localhost"):
        raw = parsed.netloc + raw
    path = Path(raw)
    if not path.is_file():
        raise ValueError(f"Prompt file not found: {uri}")
    if path.suffix != ".md":
        raise ValueError(f"Prompt file must be .md: {uri}")
    try:
        return parse_prompt_file(path)
    except Exception as e:
        raise ValueError(f"Failed to parse prompt file {uri}: {e}") from e


def parse_prompt_file(path: Path) -> Prompt:
    """Parse a .md file with optional YAML frontmatter.

    Frontmatter is recognised only when the file *starts* with a `---` line
    (Jekyll/Obsidian/Starlight convention). A bare `---` elsewhere in the body
    (a horizontal rule, a YAML example) is left untouched. The block itself is
    parsed as YAML — the project is YAML-only, so no hand-rolled key:value scan.
    """
    text = path.read_text(encoding="utf-8")
    m = re.match(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", text, re.DOTALL)
    if not m:
        return Prompt(
            name=path.stem,
            description="",
            body=text.strip(),
            source_path=str(path),
        )

    meta = yaml.safe_load(m.group(1)) or {}
    if not isinstance(meta, dict):
        meta = {}

    return Prompt(
        name=str(meta.get("name", path.stem)),
        description=str(meta.get("description", "")),
        body=m.group(2).strip(),
        source_path=str(path),
    )
