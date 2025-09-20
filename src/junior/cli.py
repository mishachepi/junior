"""Command line interface for Junior."""

import asyncio
from pathlib import Path
from typing import Optional

import structlog
import typer
from rich.console import Console
from rich.table import Table

from .config import settings
from .github_client import GitHubClient
from .models import CodeReviewRequest
from .review_agent import LogicalReviewAgent

app = typer.Typer(help="Junior - AI Agent for Code Review")
console = Console()


def setup_logging(debug: bool = False) -> None:
    """Set up structured logging."""
    level = "DEBUG" if debug else settings.log_level
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer()
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(structlog, level)
        ),
        logger_factory=structlog.WriteLoggerFactory(),
        cache_logger_on_first_use=True,
    )


@app.command()
def review_pr(
    repository: str = typer.Argument(..., help="Repository in format owner/repo"),
    pr_number: int = typer.Argument(..., help="Pull request number"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Review a specific pull request."""
    setup_logging(debug)
    
    async def _review():
        try:
            console.print(f"[bold blue]Reviewing PR #{pr_number} in {repository}[/bold blue]")
            
            # Initialize clients
            github_client = GitHubClient()
            agent = LogicalReviewAgent()
            
            # Fetch PR data
            console.print("Fetching pull request data...")
            pr_data = await github_client.get_pull_request(repository, pr_number)
            
            # Create review request
            request = CodeReviewRequest(
                repository=repository,
                pr_number=pr_number,
                title=pr_data["title"],
                description=pr_data.get("body"),
                author=pr_data["user"]["login"],
                base_branch=pr_data["base"]["ref"],
                head_branch=pr_data["head"]["ref"],
                files=await github_client.get_pr_files(repository, pr_number),
            )
            
            # Perform review
            console.print("Performing AI code review...")
            result = await agent.review_code(request)
            
            # Display results
            _display_review_result(result)
            
        except Exception as e:
            console.print(f"[bold red]Error: {e}[/bold red]")
            raise typer.Exit(1)
    
    asyncio.run(_review())


@app.command()
def review_local(
    path: str = typer.Argument(".", help="Path to git repository"),
    base_branch: str = typer.Option("main", "--base", help="Base branch for comparison"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Review local changes against a base branch."""
    setup_logging(debug)
    
    async def _review_local():
        try:
            from .git_client import GitClient
            
            console.print(f"[bold blue]Reviewing local changes in {path}[/bold blue]")
            
            # Initialize clients
            git_client = GitClient(Path(path))
            agent = LogicalReviewAgent()
            
            # Get current branch and changes
            current_branch = git_client.get_current_branch()
            console.print(f"Current branch: [cyan]{current_branch}[/cyan]")
            console.print(f"Comparing against: [cyan]{base_branch}[/cyan]")
            
            # Get file changes
            files = git_client.get_changed_files(base_branch)
            
            if not files:
                console.print("[yellow]No changes found[/yellow]")
                return
            
            # Create review request
            request = CodeReviewRequest(
                repository="local",
                pr_number=0,
                title=f"Local changes on {current_branch}",
                description="Local changes review",
                author="local",
                base_branch=base_branch,
                head_branch=current_branch,
                files=files,
            )
            
            # Perform review
            console.print("Performing AI code review...")
            result = await agent.review_code(request)
            
            # Display results
            _display_review_result(result)
            
        except Exception as e:
            console.print(f"[bold red]Error: {e}[/bold red]")
            raise typer.Exit(1)
    
    asyncio.run(_review_local())


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
    from .api import app as fastapi_app
    
    console.print(f"[bold blue]Starting Junior webhook server on {host}:{port}[/bold blue]")
    
    uvicorn.run(
        fastapi_app,
        host=host,
        port=port,
        reload=reload,
        log_level=settings.log_level.lower()
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
        "Set" if settings.openai_api_key else "Not set"
    )
    table.add_row(
        "Anthropic API Key", 
        "✓" if settings.anthropic_api_key else "✗",
        "Set" if settings.anthropic_api_key else "Not set"
    )
    table.add_row(
        "GitHub Token", 
        "✓" if settings.github_token else "✗",
        "Set" if settings.github_token else "Not set"
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
                console.print(f"[green]GitHub connection successful[/green] - User: {user['login']}")
            else:
                console.print("[red]GitHub token not configured[/red]")
                
        except Exception as e:
            console.print(f"[red]GitHub connection failed: {e}[/red]")
    
    asyncio.run(_test_connectivity())


def _display_review_result(result) -> None:
    """Display review results in a formatted table."""
    console.print("\n[bold green]Review Summary[/bold green]")
    console.print(result.summary)
    
    if result.comments:
        console.print(f"\n[bold yellow]Issues Found: {len(result.comments)}[/bold yellow]")
        
        # Group by category
        categories = {}
        for comment in result.comments:
            if comment.category not in categories:
                categories[comment.category] = []
            categories[comment.category].append(comment)
        
        for category, comments in categories.items():
            console.print(f"\n[bold cyan]{category.upper()} ({len(comments)} issues)[/bold cyan]")
            
            for comment in comments:
                severity_color = {
                    "low": "green",
                    "medium": "yellow", 
                    "high": "red",
                    "critical": "bold red"
                }.get(comment.severity, "white")
                
                console.print(f"  [{severity_color}]{comment.severity.upper()}[/{severity_color}]: {comment.message}")
                
                if comment.filename:
                    console.print(f"    File: {comment.filename}")
                if comment.line_number:
                    console.print(f"    Line: {comment.line_number}")
                if comment.suggestion:
                    console.print(f"    Suggestion: {comment.suggestion}")
                console.print()
    else:
        console.print("[green]No issues found! ✨[/green]")


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()