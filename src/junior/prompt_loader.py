"""Load review prompts from .md files with frontmatter."""

from dataclasses import dataclass
from pathlib import Path

import structlog

logger = structlog.get_logger()

BUILTIN_PROMPTS_DIR = Path(__file__).parent / "prompts"


@dataclass
class Prompt:
    name: str
    description: str
    body: str
    source_path: str


def load_prompts(names: list[str], prompts_dir: str = "") -> list[Prompt]:
    """Load prompts by name from built-in + user directories.

    Raises ValueError if any name not found.
    """
    available = discover_prompts(prompts_dir)
    result = []
    for name in names:
        name = name.strip()
        if not name:
            continue
        if name not in available:
            raise ValueError(f"Unknown prompt '{name}'. Available: {sorted(available)}")
        result.append(available[name])
    if not result:
        logger.warning("no prompts loaded — review will use model defaults only")
        return result
    logger.info(
        "prompts loaded",
        names=[p.name for p in result],
        total_body_size=sum(len(p.body) for p in result),
    )
    return result


def load_prompt_files(paths: list[str]) -> list[Prompt]:
    """Load prompts directly from file paths.

    Only .md files are accepted. Raises ValueError on any error.
    """
    result = []
    for raw_path in paths:
        path = Path(raw_path).resolve()
        if not path.is_file():
            raise ValueError(f"Prompt file not found: {raw_path}")
        if path.suffix != ".md":
            raise ValueError(f"Prompt file must be .md: {raw_path}")
        try:
            result.append(parse_prompt_file(path))
        except Exception as e:
            raise ValueError(f"Failed to parse prompt file {raw_path}: {e}") from e
    if result:
        logger.info(
            "prompt files loaded",
            names=[p.name for p in result],
            total_body_size=sum(len(p.body) for p in result),
        )
    return result


def discover_prompts(prompts_dir: str = "") -> dict[str, Prompt]:
    """Scan built-in prompts + optional user directory. User overrides built-in on name collision."""
    prompts: dict[str, Prompt] = {}

    for path in sorted(BUILTIN_PROMPTS_DIR.glob("*.md")):
        prompt = parse_prompt_file(path)
        prompts[prompt.name] = prompt

    if prompts_dir:
        user_dir = Path(prompts_dir).resolve()
        if user_dir.is_dir():
            for path in sorted(user_dir.glob("*.md")):
                prompt = parse_prompt_file(path)
                prompts[prompt.name] = prompt
            logger.debug("user prompts dir scanned", path=str(user_dir))
        else:
            raise ValueError(f"PROMPTS_DIR not found: {prompts_dir}")

    return prompts


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
