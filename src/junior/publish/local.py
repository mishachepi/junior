"""Local publisher backend — renders the review as Markdown to stdout."""

from junior.config import Settings
from junior.runbooks.code_review.models import ReviewResult
from junior.publish.core import format_summary


def post_review(settings: Settings, result: ReviewResult) -> None:
    """Render the review as Markdown to stdout.

    `--publish` on `local_review` means "render the review"; it always goes to
    stdout — redirect with `> file` to save it. (`-o`/`output_file` is the raw
    JSON sink for runs *without* `--publish`.)
    """
    formatted = format_summary(result, settings=settings)

    from junior.cli.console import console, err_console, print_content

    # Label goes to stderr so a piped/redirected stdout stays pure markdown.
    err_console.rule("[bold]Review[/]")
    if console.is_terminal:
        from rich.markdown import Markdown

        console.print(Markdown(formatted))  # pretty render for humans
    else:
        print_content(formatted)  # raw markdown for pipes/files
