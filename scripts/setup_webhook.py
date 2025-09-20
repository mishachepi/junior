#!/usr/bin/env python3
"""Setup script for configuring GitHub webhook integration."""

import asyncio
import json
import sys
from pathlib import Path

import httpx
import typer
from rich.console import Console
from rich.table import Table

console = Console()


def main(
    repository: str = typer.Argument(..., help="Repository in format owner/repo"),
    webhook_url: str = typer.Argument(..., help="Webhook URL (e.g., https://your-domain.com/webhook/github)"),
    github_token: str = typer.Option(..., "--token", help="GitHub personal access token"),
    webhook_secret: str = typer.Option(None, "--secret", help="Webhook secret (optional but recommended)"),
    events: str = typer.Option("pull_request", "--events", help="Comma-separated list of events"),
):
    """Set up GitHub webhook for Junior code review agent."""
    
    console.print(f"[bold blue]Setting up webhook for {repository}[/bold blue]")
    
    asyncio.run(setup_webhook(repository, webhook_url, github_token, webhook_secret, events.split(",")))


async def setup_webhook(repository: str, webhook_url: str, github_token: str, webhook_secret: str, events: list):
    """Set up the GitHub webhook."""
    
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json"
    }
    
    webhook_config = {
        "name": "web",
        "active": True,
        "events": events,
        "config": {
            "url": webhook_url,
            "content_type": "json",
            "insecure_ssl": "0"
        }
    }
    
    if webhook_secret:
        webhook_config["config"]["secret"] = webhook_secret
    
    try:
        async with httpx.AsyncClient() as client:
            # Check if repository exists and we have access
            repo_response = await client.get(
                f"https://api.github.com/repos/{repository}",
                headers=headers
            )
            
            if repo_response.status_code != 200:
                console.print(f"[red]Error: Cannot access repository {repository}[/red]")
                console.print(f"Status: {repo_response.status_code}")
                console.print(f"Response: {repo_response.text}")
                return
            
            repo_data = repo_response.json()
            console.print(f"✅ Repository found: {repo_data['full_name']}")
            
            # Check existing webhooks
            webhooks_response = await client.get(
                f"https://api.github.com/repos/{repository}/hooks",
                headers=headers
            )
            
            if webhooks_response.status_code == 200:
                existing_webhooks = webhooks_response.json()
                
                # Check if webhook already exists
                for hook in existing_webhooks:
                    if hook.get("config", {}).get("url") == webhook_url:
                        console.print(f"[yellow]Webhook already exists with ID {hook['id']}[/yellow]")
                        
                        update = typer.confirm("Do you want to update the existing webhook?")
                        if update:
                            # Update webhook
                            update_response = await client.patch(
                                f"https://api.github.com/repos/{repository}/hooks/{hook['id']}",
                                headers=headers,
                                json=webhook_config
                            )
                            
                            if update_response.status_code == 200:
                                console.print("✅ Webhook updated successfully!")
                                display_webhook_info(update_response.json())
                            else:
                                console.print(f"[red]Failed to update webhook: {update_response.text}[/red]")
                        return
            
            # Create new webhook
            create_response = await client.post(
                f"https://api.github.com/repos/{repository}/hooks",
                headers=headers,
                json=webhook_config
            )
            
            if create_response.status_code == 201:
                console.print("✅ Webhook created successfully!")
                webhook_data = create_response.json()
                display_webhook_info(webhook_data)
                
                # Test the webhook
                console.print("\n[bold yellow]Testing webhook...[/bold yellow]")
                test_response = await client.post(
                    f"https://api.github.com/repos/{repository}/hooks/{webhook_data['id']}/tests",
                    headers=headers
                )
                
                if test_response.status_code == 204:
                    console.print("✅ Webhook test successful!")
                else:
                    console.print(f"[yellow]Webhook test failed: {test_response.status_code}[/yellow]")
                
            else:
                console.print(f"[red]Failed to create webhook: {create_response.status_code}[/red]")
                console.print(f"Response: {create_response.text}")
    
    except Exception as e:
        console.print(f"[red]Error setting up webhook: {e}[/red]")


def display_webhook_info(webhook_data: dict):
    """Display webhook information in a table."""
    table = Table(title="Webhook Information")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("ID", str(webhook_data.get("id")))
    table.add_row("URL", webhook_data.get("config", {}).get("url"))
    table.add_row("Events", ", ".join(webhook_data.get("events", [])))
    table.add_row("Active", str(webhook_data.get("active")))
    table.add_row("Created", webhook_data.get("created_at"))
    table.add_row("Updated", webhook_data.get("updated_at"))
    
    console.print(table)
    
    # Display next steps
    console.print("\n[bold green]Next Steps:[/bold green]")
    console.print("1. Ensure your Junior webhook service is running and accessible")
    console.print("2. Create a test pull request to verify the integration")
    console.print("3. Check the webhook service logs for any issues")
    console.print("4. Monitor the webhook deliveries in GitHub repository settings")


if __name__ == "__main__":
    typer.run(main)