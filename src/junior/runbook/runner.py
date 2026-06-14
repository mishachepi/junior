"""The generic runner — ties a runbook to a harness for one review.

Domain-agnostic: it never mentions diffs, MRs, or Jira. Given an already-collected
context (collection is the caller's concern, so `--from-file` can bypass it), it
asks the harness for the runbook's result schema and hands the result to the
runbook to publish.
"""

from __future__ import annotations

from junior.config import Settings
from junior.runbook.base import Harness, LLMResult, Runbook
from junior.prompt_loader import load_prompts


def merge_system_prompt(base: str, extra: list[str]) -> str:
    """Append user-supplied system-prompt layers onto the runbook default.

    `extra` entries are inline text or `file://...` URIs (resolved here)."""
    bodies = [p.body for p in load_prompts(extra)]
    parts = [p for p in (base, *bodies) if p and p.strip()]
    return "\n\n".join(parts)


def run_runbook(
    runbook: Runbook,
    harness: Harness,
    context,
    settings: Settings,
    *,
    publish_enabled: bool,
) -> LLMResult:
    """Complete on an already-collected context. Returns the LLMResult.

    When `publish_enabled`, the runbook's custom `publish()` runs (post/render/…).
    Otherwise nothing is emitted here — the CLI writes `render_output()` to
    stdout/`-o`. Either way the run record captures the full result.
    """
    result = harness.complete(
        system_prompt=merge_system_prompt(
            runbook.system_prompt(settings),
            list(settings.llm.system_prompt),
        ),
        user_message=runbook.render(context, settings, file_access=harness.file_access),
        output_schema=runbook.result_model,
        settings=settings,
    )
    if publish_enabled:
        runbook.publish(settings, result.output, result.usage, errors=result.errors)
    return result
