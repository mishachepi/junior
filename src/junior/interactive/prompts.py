"""Individual interactive prompts (questionary wrappers).

These are pure UI primitives — each function asks one question and returns
the answer (or `None` on Ctrl+C). The orchestrator in
`junior.interactive.__init__` composes them into the full wizard.
"""

from __future__ import annotations

import questionary


def _match_default(
    choices: list[questionary.Choice], value: str | None
) -> questionary.Choice | None:
    """questionary.select needs the Choice object matching a value, not the raw value."""
    if value is None:
        return None
    for choice in choices:
        if choice.value == value:
            return choice
    return None


def ask_config_target(default: str = "global") -> str | None:
    """Where to save the config: 'global' (your default) or 'local' (this project)."""
    choices = [
        questionary.Choice(
            "global — ~/.config/junior/settings.yaml (your default for every repo)",
            value="global",
        ),
        questionary.Choice(
            "local — ./.junior.yaml (this project only; commit to share with the team)",
            value="local",
        ),
    ]
    return questionary.select(
        "Where should this config be saved:",
        choices=choices,
        default=_match_default(choices, default),
    ).ask()


def ask_runbook(names: list[str], default: str | None = None) -> str | None:
    """Pick the runbook (what gets reviewed and where the result is posted)."""
    from junior.runbook.registry import available_runbooks_meta

    desc = dict(available_runbooks_meta())
    choices = [
        questionary.Choice(
            f"{n} — {desc.get(n) or 'custom runbook'}", value=n
        )
        for n in names
    ]
    return questionary.select(
        "Runbook (what to review & where to post):",
        choices=choices,
        default=_match_default(choices, default),
    ).ask()


def ask_publish(default: bool = False) -> bool | None:
    """Whether to auto-post the review to the platform (None on cancel)."""
    return questionary.confirm(
        "Publish the review to the platform automatically?",
        default=default,
    ).ask()


def ask_harness(default: str | None = None) -> str | None:
    """Pick the LLM harness. Returns short name or None on cancel."""
    choices = [
        questionary.Choice("claudecode — uses local Claude CLI (no API key needed)", value="claudecode"),
        questionary.Choice("pydantic — single structured call via OpenAI/Anthropic API", value="pydantic"),
        questionary.Choice("codex — uses local Codex CLI", value="codex"),
        questionary.Choice("deepagents — LangChain orchestrator + subagents", value="deepagents"),
        questionary.Choice("pi — pi CLI; local models via ~/.pi/agent/models.json", value="pi"),
    ]
    return questionary.select(
        "Harness (which AI runs the review):",
        choices=choices,
        default=_match_default(choices, default),
    ).ask()


def ask_model(default: str | None, harness: str) -> str | None:
    """Pick model spec.

    Accepts either bare model name (provider inferred from API key) or
    provider-prefixed `provider:model`. Empty allowed for codex/claudecode.
    """
    hint = {
        "pydantic": "e.g. anthropic:claude-opus-4-6, gpt-5.4-mini",
        "deepagents": "e.g. anthropic:claude-opus-4-6, gpt-5.4-mini",
        "claudecode": "leave empty to let the CLI choose",
        "codex": "ignored — codex CLI picks its own model",
    }.get(harness, "")
    return questionary.text(
        f"Model spec ({hint}):" if hint else "Model spec:",
        default=default or "",
    ).ask()


def ask_source(default: str | None = None) -> str | None:
    """Pick source mode."""
    choices = [
        questionary.Choice("auto — smart detection (CI base, branch diff, or uncommitted)", value="auto"),
        questionary.Choice("staged — staged changes only (git diff --cached)", value="staged"),
        questionary.Choice("commit — last commit (git diff HEAD~1)", value="commit"),
        questionary.Choice("branch — current branch vs target branch", value="branch"),
    ]
    return questionary.select(
        "Source (what to review):",
        choices=choices,
        default=_match_default(choices, default),
    ).ask()


def ask_target_branch(default: str = "main") -> str | None:
    """Target branch for the branch diff."""
    return questionary.text(
        "Target branch (for diff comparison):",
        default=default,
    ).ask()


def ask_output_mode(default: str = "stdout") -> str | None:
    """Pick where to publish the review."""
    choices = [
        questionary.Choice("stdout — print to console", value="stdout"),
        questionary.Choice("file — write to a markdown file", value="file"),
        questionary.Choice("publish — post to GitLab MR / GitHub PR", value="publish"),
    ]
    return questionary.select(
        "Output target:",
        choices=choices,
        default=_match_default(choices, default),
    ).ask()


def ask_output_file(default: str = "review.md") -> str | None:
    """Filename to write the review into."""
    return questionary.text(
        "Output file path:",
        default=default,
    ).ask()


def confirm_run(summary: str) -> bool:
    """Show summary and ask to proceed."""
    questionary.print(summary)
    answer = questionary.confirm("Run now?", default=True).ask()
    return bool(answer)
