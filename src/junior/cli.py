"""Command line interface for Junior. Requred for testing."""

import asyncio

import structlog
import typer
from rich.console import Console
from rich.table import Table

from .config import settings
from .services import GitHubClient

app = typer.Typer(help="Junior - AI Agent for Code Review")
console = Console()


def setup_logging(debug: bool = False) -> None:
    """Set up structured logging."""
    import logging

    level = "DEBUG" if debug else settings.log_level
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper())
        ),
        logger_factory=structlog.WriteLoggerFactory(),
        cache_logger_on_first_use=True,
    )


# Review commands removed - use the webhook server for PR reviews
# Manual PR review can be done via the /review endpoint


@app.command()
def webhook_server(
    host: str = typer.Option("0.0.0.0", "--host", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", help="Port to bind to"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Start the webhook server."""
    setup_logging(debug)

    import uvicorn

    from .app import app as fastapi_app

    console.print(
        f"[bold blue]Starting Junior webhook server on {host}:{port}[/bold blue]"
    )

    uvicorn.run(
        fastapi_app,
        host=host,
        port=port,
        reload=reload,
        log_level=settings.log_level.lower(),
    )


@app.command()
def config_check() -> None:
    """Check configuration and API connectivity."""
    setup_logging()

    table = Table(title="Configuration Status")
    table.add_column("Setting", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Value", style="yellow")

    # Check API keys
    table.add_row(
        "OpenAI API Key",
        "✓" if settings.openai_api_key else "✗",
        "Set" if settings.openai_api_key else "Not set",
    )
    table.add_row(
        "Anthropic API Key",
        "✓" if settings.anthropic_api_key else "✗",
        "Set" if settings.anthropic_api_key else "Not set",
    )
    table.add_row(
        "GitHub Token",
        "✓" if settings.github_token else "✗",
        "Set" if settings.github_token else "Not set",
    )

    # Check other settings
    table.add_row("Default Model", "✓", settings.default_model)
    table.add_row("Log Level", "✓", settings.log_level)
    table.add_row("Database URL", "✓", settings.database_url)

    console.print(table)

    # Test API connectivity
    async def _test_connectivity():
        try:
            if settings.github_token:
                github_client = GitHubClient()
                user = await github_client.get_authenticated_user()
                console.print(
                    f"[green]GitHub connection successful[/green] - User: {user['login']}"
                )
            else:
                console.print("[red]GitHub token not configured[/red]")

        except Exception as e:
            console.print(f"[red]GitHub connection failed: {e}[/red]")

    asyncio.run(_test_connectivity())


# Display functions removed - use webhook server for reviews


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
