"""Local publisher backend — prints review to stdout or writes to file."""

from pathlib import Path

import structlog

from junior.config import Settings
from junior.models import ReviewResult
from junior.publish.core import format_summary

logger = structlog.get_logger()


def post_review(settings: Settings, result: ReviewResult) -> None:
    """Output formatted review to stdout or file."""
    formatted = format_summary(result, settings=settings)

    if settings.publish_output:
        output_path = Path(settings.publish_output)
        output_path.write_text(formatted, encoding="utf-8")
        logger.info("review written to file", path=str(output_path))
    else:
        print("\n--- Review Output ---\n")
        print(formatted)
