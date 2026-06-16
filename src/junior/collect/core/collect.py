"""Shared collection runbook — used by all collector backends.

Runbook: git diff -> parse files -> commit messages -> extra context.
Enrichment (MR metadata from API) is NOT included — each backend adds its own.
"""

from pathlib import Path

import structlog

from junior.collect.core.diff import (
    get_commit_messages,
    get_diff,
    parse_changed_files,
    resolve_base_sha,
)
from junior.config import Settings
from junior.runbooks.code_review.models import ReviewContext, MRComment

logger = structlog.get_logger()


def collect_base(settings: Settings) -> ReviewContext:
    """Collect base context without platform-specific enrichment.

    Steps:
    1. Git diff + changed files
    2. Commit messages
    3. Extra context from --context (text) and --context-file (files)

    Returns ReviewContext with mr_description/labels from env vars only.
    Backend modules should enrich with API data after calling this.

    Explicit input text (the positional CLI argument) replaces the git diff as
    the review subject: no git calls, the text goes into `full_diff` verbatim.
    """
    input_text = settings.context.input_text
    if input_text:
        logger.info("reviewing provided input text instead of a git diff", size=len(input_text))
        context = ReviewContext(
            mr_title=settings.context.mr_title,
            full_diff=input_text,
            extra_context=dict(settings.context.context),
        )
        return _apply_context_files(context, settings.context.context_files)

    project_dir = Path(settings.context.project_dir)
    target_branch = settings.context.target_branch
    base_sha, base_source = resolve_base_sha(settings)

    logger.debug(
        "collecting context",
        project_dir=str(project_dir),
        target_branch=target_branch,
        base_sha=base_sha or "(none)",
        base_source=base_source,
    )

    # 1. Git diff
    full_diff, diff_desc = get_diff(
        project_dir, target_branch, base_sha,
        source=settings.context.source.value, base_source=base_source,
    )
    changed_files = parse_changed_files(full_diff, project_dir, settings.llm.max_file_size)
    logger.debug("diff parsed", source=diff_desc, diff_size=len(full_diff), changed_files=len(changed_files))

    # 2. Commit messages
    commit_messages = get_commit_messages(project_dir, target_branch, base_sha)

    context = ReviewContext(
        project_id=settings.output.ci_project_id or 0,
        mr_iid=settings.output.ci_merge_request_iid or 0,
        mr_title=settings.context.mr_title,
        mr_description=settings.context.mr_description,
        source_branch=settings.context.source_branch,
        target_branch=target_branch,
        labels=[],
        commit_messages=commit_messages,
        full_diff=full_diff,
        changed_files=changed_files,
        extra_context=dict(settings.context.context),
    )

    # 3. Process --context-file entries
    context = _apply_context_files(context, settings.context.context_files)

    return context


def enrich_with_metadata(
    context: ReviewContext,
    description: str,
    labels: list[str],
    comments: list[MRComment] | None = None,
) -> ReviewContext:
    """Update context with API-fetched MR metadata (description, labels, comments)."""
    updates = {}
    if description and not context.mr_description:
        updates["mr_description"] = description
    if labels:
        updates["labels"] = labels
    if comments:
        updates["comments"] = comments
    return context.model_copy(update=updates) if updates else context


# --- Context file processing ---


def _apply_context_files(
    context: ReviewContext,
    context_files: dict[str, str],
) -> ReviewContext:
    """Process --context-file entries.

    All files are read as raw text and added to extra_context.
    """
    for key, path in context_files.items():
        context = _load_raw_context_file(context, key, path)
    return context


def _load_raw_context_file(context: ReviewContext, key: str, path: str) -> ReviewContext:
    """Read a file as text and add to extra_context under the given key."""
    content = Path(path).read_text(encoding="utf-8", errors="ignore")
    extra = {**context.extra_context, key: content}
    logger.debug("loaded context file", key=key, path=path, size=len(content))
    return context.model_copy(update={"extra_context": extra})
