"""Load review prompts.

Junior is a thin wrapper — it doesn't ship its own prompts. The user supplies
each prompt as either inline text or a `file://...` URI pointing at a `.md`
file. Both shapes flow through `context.prompts` (one list).

Examples live in `docs-site/src/content/docs/examples/prompts/` (not loaded automatically).
"""

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

import structlog

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
    """Parse a .md file with ---frontmatter--- body format."""
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", maxsplit=2)

    if len(parts) < 3:
        return Prompt(
            name=path.stem,
            description="",
            body=text.strip(),
            source_path=str(path),
        )

    meta: dict[str, str] = {}
    for line in parts[1].strip().splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()

    return Prompt(
        name=meta.get("name", path.stem),
        description=meta.get("description", ""),
        body=parts[2].strip(),
        source_path=str(path),
    )
