"""Helpers shared by the text-CLI harnesses (codex, pi).

These harnesses have no native structured-output mode: the model answers with
prose that *contains* a JSON object, so Junior strips code fences / surrounding
text and validates the JSON against the requested schema itself.
"""

from __future__ import annotations

import json

import structlog
from pydantic import BaseModel

logger = structlog.get_logger()


def parse_json_reply(text: str, output_schema: type[BaseModel], *, source: str) -> BaseModel:
    """Extract the outermost JSON object from `text` and validate it.

    Tolerant by design: drops ```fences``` and any prose around the object.
    `source` names the harness in log/error messages (e.g. "codex", "pi").
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.find("\n")
        cleaned = cleaned[first_newline + 1 :] if first_newline >= 0 else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].rstrip()

    json_start = cleaned.find("{")
    json_end = cleaned.rfind("}") + 1
    if json_start >= 0 and json_end > json_start:
        cleaned = cleaned[json_start:json_end]

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error(f"{source} output is not valid JSON", output=cleaned[:500], error=str(e))
        raise RuntimeError(f"Failed to parse {source} output as JSON: {e}")

    try:
        return output_schema.model_validate(data)
    except Exception as e:
        logger.error(f"{source} output failed validation", data=data, error=str(e))
        raise RuntimeError(f"{source} output failed {output_schema.__name__} validation: {e}")
