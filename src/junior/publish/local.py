"""Local publisher backend — prints review to stdout or writes to file."""

from pathlib import Path

import structlog

from junior.config import Settings
from junior.runbooks.code_review.models import ReviewResult
from junior.publish.core import format_summary

logger = structlog.get_logger()


def post_review(settings: Settings, result: ReviewResult) -> None:
    """Output formatted review to stdout or file."""
    formatted = format_summary(result, settings=settings)

    if settings.output.output_file:
        output_path = Path(settings.output.output_file)
        output_path.write_text(formatted, encoding="utf-8")
        logger.info("review written to file", path=str(output_path))
        return

    from junior.cli.console import console, err_console, print_content

    # Label goes to stderr so a piped/redirected stdout stays pure markdown.
    err_console.rule("[bold]Review[/]")
    if console.is_terminal:
        from rich.markdown import Markdown

        console.print(Markdown(formatted))  # pretty render for humans
    else:
        print_content(formatted)  # raw markdown for pipes/files
