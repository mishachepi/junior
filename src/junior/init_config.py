"""Interactive setup for Junior — saves config to ~/.config/junior/config.json."""

import os

import questionary

from junior.config import GLOBAL_CONFIG_PATH, save_global_config


def interactive_setup() -> None:
    """Interactive setup — choose backend, provider, prompts."""
    print("Junior — interactive setup")
    print(f"This will save your defaults to {GLOBAL_CONFIG_PATH}")
    print("(API keys stay in env vars — they're not written to the file.)\n")

    if GLOBAL_CONFIG_PATH.is_file():
        if not questionary.confirm(
            "Config already exists. Overwrite?",
            default=False,
        ).ask():
            print("Cancelled. Existing config kept.")
            return

    backend = questionary.select(
        "Backend (which AI runs the review):",
        choices=[
            questionary.Choice("claudecode — uses local Claude CLI (no API key needed)", value="claudecode"),
            questionary.Choice("pydantic — parallel agents via OpenAI/Anthropic API", value="pydantic"),
            questionary.Choice("codex — uses local Codex CLI", value="codex"),
        ],
    ).ask()
    if backend is None:
        return

    config: dict = {"agent_backend": backend}
    provider = None

    if backend == "pydantic":
        provider = questionary.select(
            "Provider:",
            choices=[
                questionary.Choice("openai — uses OPENAI_API_KEY", value="openai"),
                questionary.Choice("anthropic — uses ANTHROPIC_API_KEY", value="anthropic"),
            ],
        ).ask()
        if provider is None:
            return

        config["model_provider"] = provider

    prompts = questionary.text(
        "Prompts to run (comma-separated):",
        default="security,logic,design",
    ).ask()
    if prompts is None:
        return
    if prompts != "security,logic,design":
        config["prompts"] = prompts

    path = save_global_config(config)

    # Summary + next steps
    print("\nConfiguration saved.")
    print(f"  Backend  : {backend}")
    if provider:
        print(f"  Provider : {provider}")
    print(f"  Prompts  : {prompts}")
    print(f"  File     : {path}")

    if backend == "pydantic":
        env_var = "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
        if not os.environ.get(env_var):
            print(f"\nReminder: set {env_var} in your shell before running Junior:")
            print(f"  export {env_var}=...")

    print("\nNext: cd into your repo, check out the branch you want reviewed, then run:")
    print("  junior --dry-run        # preview")
    print("  junior                  # actually review")
