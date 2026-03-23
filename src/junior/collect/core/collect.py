"""Shared collection pipeline — used by all collector backends.

Pipeline: git diff -> parse files -> commit messages -> extra context.
Enrichment (MR metadata from API) is NOT included — each backend adds its own.
"""

from pathlib import Path

import structlog

from junior.collect.core.diff import get_commit_messages, get_diff, parse_changed_files
from junior.config import Settings
from junior.models import CollectedContext

logger = structlog.get_logger()


def collect_base(settings: Settings) -> CollectedContext:
    """Collect base context without platform-specific enrichment.

    Steps:
    1. Git diff + changed files
    2. Commit messages
    3. Extra context from --context (text) and --context-file (files)

    Returns CollectedContext with mr_description/labels from env vars only.
    Backend modules should enrich with API data after calling this.
    """
    project_dir = Path(settings.ci_project_dir)
    target_branch = settings.ci_merge_request_target_branch_name
    base_sha = settings.ci_merge_request_diff_base_sha

    logger.info(
        "collecting context",
        project_dir=str(project_dir),
        target_branch=target_branch,
        base_sha=base_sha or "(none)",
    )

    # 1. Git diff
    full_diff = get_diff(project_dir, target_branch, base_sha)
    changed_files = parse_changed_files(full_diff, project_dir, settings.max_file_size)
    logger.info("parsed diff", diff_size=len(full_diff), changed_files=len(changed_files))

    # 2. Commit messages
    commit_messages = get_commit_messages(project_dir, target_branch, base_sha)

    context = CollectedContext(
        project_id=settings.ci_project_id or 0,
        mr_iid=settings.ci_merge_request_iid or 0,
        mr_title=settings.ci_merge_request_title,
        mr_description=settings.ci_merge_request_description,
        source_branch=settings.ci_merge_request_source_branch_name,
        target_branch=target_branch,
        labels=[],
        commit_messages=commit_messages,
        full_diff=full_diff,
        changed_files=changed_files,
        extra_context=dict(settings.context),
    )

    # 4. Process --context-file entries
    context = _apply_context_files(context, settings.context_files)

    return context


def enrich_with_metadata(
    context: CollectedContext,
    description: str,
    labels: list[str],
) -> CollectedContext:
    """Update context with API-fetched MR metadata (description, labels)."""
    updates = {}
    if description and not context.mr_description:
        updates["mr_description"] = description
    if labels:
        updates["labels"] = labels
    return context.model_copy(update=updates) if updates else context


# --- Context file processing ---


def _apply_context_files(
    context: CollectedContext,
    context_files: dict[str, str],
) -> CollectedContext:
    """Process --context-file entries.

    All files are read as raw text and added to extra_context.
    """
    for key, path in context_files.items():
        context = _load_raw_context_file(context, key, path)
    return context


def _load_raw_context_file(context: CollectedContext, key: str, path: str) -> CollectedContext:
    """Read a file as text and add to extra_context under the given key."""
    content = Path(path).read_text(encoding="utf-8", errors="ignore")
    extra = {**context.extra_context, key: content}
    logger.info("loaded context file", key=key, path=path, size=len(content))
    return context.model_copy(update={"extra_context": extra})
