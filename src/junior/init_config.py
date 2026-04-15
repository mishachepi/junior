"""Interactive setup for Junior — saves config to ~/.config/junior/config.json."""

import os

import questionary

from junior.config import GLOBAL_CONFIG_PATH, save_global_config


def interactive_setup() -> None:
    """Interactive setup — choose backend, provider, prompts."""
    print("Junior — Interactive Setup\n")

    if GLOBAL_CONFIG_PATH.is_file():
        if not questionary.confirm(
            f"Config already exists at {GLOBAL_CONFIG_PATH}. Overwrite?",
            default=False,
        ).ask():
            return

    backend = questionary.select(
        "Choose a backend:",
        choices=[
            questionary.Choice("claudecode — uses Claude CLI (default, no API key)", value="claudecode"),
            questionary.Choice("pydantic — parallel agents via API key", value="pydantic"),
            questionary.Choice("codex — uses Codex CLI", value="codex"),
        ],
    ).ask()
    if backend is None:
        return

    config: dict = {"agent_backend": backend}

    if backend == "pydantic":
        provider = questionary.select(
            "Choose a provider:",
            choices=[
                questionary.Choice("openai — requires OPENAI_API_KEY", value="openai"),
                questionary.Choice("anthropic — requires ANTHROPIC_API_KEY", value="anthropic"),
            ],
        ).ask()
        if provider is None:
            return

        config["model_provider"] = provider

        env_var = "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
        if not os.environ.get(env_var):
            print(f"\n  Set your API key as an environment variable (not stored in config):")
            print(f"  export {env_var}=sk-...\n")

    prompts = questionary.text(
        "Prompts (comma-separated):",
        default="security,logic,design",
    ).ask()
    if prompts is None:
        return
    if prompts != "security,logic,design":
        config["prompts"] = prompts

    path = save_global_config(config)
    print(f"\nSaved to {path}")
    print("Run: junior --dry-run")
