"""Interactive setup for Junior — saves config to a YAML file (global or project)."""

import os
from pathlib import Path

import questionary

from junior.cli.console import console
from junior.config import (
    GLOBAL_CONFIG_PATH,
    LOCAL_CONFIG_CANDIDATES,
    save_global_config,
    save_local_config,
)
from junior.interactive import (
    ask_config_target,
    ask_harness,
    ask_model,
    ask_output_file,
    ask_runbook,
    ask_publish,
)


def interactive_setup() -> None:
    """Walk through the main settings and save them to a YAML config (global
    default or project-local). Each step explains what it configures. API keys
    are never written here — keep them in env vars."""
    console.print("[bold]Junior — interactive setup[/]")
    console.print(
        "We'll set your defaults. At run time the priority is: "
        "CLI flags > env vars > this config file.\n"
    )

    # --- 1. Where to save -------------------------------------------------
    console.print("[bold]1. Config location[/] — where these defaults are stored.")
    console.print(
        "[dim]  global → ~/.config/junior/settings.yaml (applies to every repo)\n"
        "  local  → ./.junior.yaml (this project only; commit it to share)[/]"
    )
    target = ask_config_target()
    if target is None:
        return
    is_local = target == "local"
    path = Path(LOCAL_CONFIG_CANDIDATES[0]) if is_local else GLOBAL_CONFIG_PATH

    if path.is_file():
        if not questionary.confirm(
            f"{path} already exists. Update it? (other keys are kept)",
            default=False,
        ).ask():
            console.print("Cancelled. Existing config kept.")
            return

    # --- 2. Runbook ------------------------------------------------------
    console.print("\n[bold]2. Runbook[/] — what gets reviewed and where the result goes.")
    console.print(
        "[dim]  local_review        → your local git diff → raw JSON (--publish: Markdown, default)\n"
        "  github_pr_review    → a GitHub PR → posts review comments\n"
        "  gitlab_pr_review    → a GitLab MR → posts a note + inline threads\n"
        "  bitbucket_pr_review → a Bitbucket DC PR → posts comment + inline comments[/]"
    )
    from junior.runbook.registry import available_runbooks

    runbook = ask_runbook(available_runbooks(), default="local_review")
    if runbook is None:
        return

    # --- 3. Harness -------------------------------------------------------
    console.print("\n[bold]3. Harness[/] — which AI engine actually runs the review.")
    console.print(
        "[dim]  claudecode / codex → drive a local CLI (no API key)\n"
        "  pydantic / deepagents → call an LLM API (key from your env)[/]"
    )
    harness = ask_harness(default="claudecode")
    if harness is None:
        return

    model = None
    if harness in ("pydantic", "deepagents"):
        console.print(
            "[dim]  Model for the API harness as `provider:model` "
            "(e.g. anthropic:claude-opus-4-6). The API key stays in env.[/]"
        )
        model = ask_model(default="", harness=harness)
        if model is None:
            return
        model = model.strip()

    # --- 4. Publish (only meaningful for platform runbooks) --------------
    publish = False
    if runbook != "local_review":
        console.print("\n[bold]4. Publish[/] — post the review to the platform automatically?")
        console.print(
            "[dim]  on  → Junior posts the PR/MR comment on every run\n"
            "  off → the review is only printed/saved; you post it yourself[/]"
        )
        answer = ask_publish(default=False)
        if answer is None:
            return
        publish = answer
    else:
        console.print("\n[dim]4. Publish — skipped (local_review can't publish).[/]")

    # --- 5. Output file (optional) ---------------------------------------
    console.print("\n[bold]5. Output file[/] (optional) — write the review to a file.")
    console.print("[dim]  Leave empty to print to stdout. e.g. review.md[/]")
    output_file = ask_output_file(default="")
    if output_file is None:
        return
    output_file = output_file.strip()

    # --- Build + save (flat shorthand form) ------------------------------
    config: dict = {"runbook": runbook, "harness": harness}
    if model:
        config["model"] = model
    if publish:
        config["publish"] = True
    if output_file:
        config["output_file"] = output_file

    saved = save_local_config(config) if is_local else save_global_config(config)

    console.print("\n[bold green]Configuration saved.[/]")
    console.print(f"  File     : {saved}")
    console.print(f"  Runbook : {runbook}")
    console.print(f"  Harness  : {harness}")
    if model:
        console.print(f"  Model    : {model}")
    if runbook != "local_review":
        console.print(f"  Publish  : {publish}")
    console.print(f"  Output   : {output_file or 'stdout'}")

    # API-key reminder for API harnesses
    if harness in ("pydantic", "deepagents"):
        provider = model.partition(":")[0].lower() if model and ":" in model else ""
        env_var = (
            f"{provider.upper()}_API_KEY" if provider
            else "OPENAI_API_KEY or ANTHROPIC_API_KEY"
        )
        already_set = (
            os.environ.get(env_var) if provider else
            (os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"))
        )
        if not already_set:
            console.print(f"\n[yellow]Reminder:[/] set {env_var} in your shell before running Junior:")
            console.print(f"  export {env_var.split(' or ')[0]}=...")

    console.print("\nPrompts (the LLM instructions) are supplied at run time:")
    console.print("  junior run --prompt 'Check security issues' --prompt 'Check logic'")
    console.print("  junior run --prompt-file my-review.md")
    console.print(
        "  ...or add a 'context.prompts' list to the config file "
        "(inline text or 'file://./path.md')."
    )
    console.print("\nNext: check out the branch you want reviewed, then run:")
    console.print("  junior dry-run          # preview what the harness will get (no AI)")
    console.print("  junior run              # actually review")
