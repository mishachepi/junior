"""Git diff operations: get diff, parse into files, commit messages."""

import subprocess
from pathlib import Path

import structlog

from junior.models import ChangedFile, FileStatus

logger = structlog.get_logger()


def get_diff(project_dir: Path, target_branch: str, base_sha: str | None) -> str:
    """Get unified diff using the best available strategy.

    Branch-based strategies (MR/PR context):
    1. base_sha...HEAD              — CI exact merge base
    2. target_branch...HEAD         — local branch, three-dot
    3. origin/target_branch...HEAD  — after remote fetch
    4. target_branch HEAD           — two-dot fallback

    If a branch strategy succeeds (even with empty output), we stop.
    Empty diff from a valid branch comparison = no changes.

    Local fallbacks (only if all branch strategies fail):
    5. HEAD                         — uncommitted changes (staged + unstaged)
    6. --cached                     — staged only (no commits yet)
    """
    # base_sha from CI is always authoritative — try it first regardless of branch
    if base_sha:
        diff = _run_git(project_dir, ["diff", f"{base_sha}...HEAD"])
        if diff is not None:
            logger.info("reviewing", strategy=f"{base_sha}...HEAD", has_changes=bool(diff.strip()))
            return diff

    # Check if we're on the target branch (no MR context)
    current_branch = _run_git(project_dir, ["rev-parse", "--abbrev-ref", "HEAD"])
    on_target = current_branch is not None and current_branch.strip() == target_branch

    # Branch-based strategies (skip if on target branch)
    if not on_target:
        diff = _run_git(project_dir, ["diff", f"{target_branch}...HEAD"])
        if diff is not None and diff.strip():
            logger.info("reviewing", strategy=f"{target_branch}...HEAD")
            return diff

        if diff is not None and not diff.strip():
            local = _run_git(project_dir, ["diff", "HEAD"])
            if local is not None and local.strip():
                logger.info("reviewing", strategy=f"{target_branch}...HEAD + uncommitted")
                return diff + local

        _run_git(project_dir, ["fetch", "origin", target_branch], allow_failure=True)
        diff = _run_git(project_dir, ["diff", f"origin/{target_branch}...HEAD"])
        if diff is not None and diff.strip():
            logger.info("reviewing", strategy=f"origin/{target_branch}...HEAD")
            return diff

        diff = _run_git(project_dir, ["diff", target_branch, "HEAD"])
        if diff is not None and diff.strip():
            logger.info("reviewing", strategy=f"{target_branch} HEAD")
            return diff

    # --- Local fallbacks ---
    logger.info("reviewing local changes", on_target_branch=on_target)

    diff = _run_git(project_dir, ["diff", "HEAD"])
    if diff is not None and diff.strip():
        logger.info("reviewing", strategy="HEAD (uncommitted)")
        return diff

    diff = _run_git(project_dir, ["diff", "--cached"])
    if diff is not None and diff.strip():
        logger.info("reviewing", strategy="--cached (staged only)")
        return diff

    logger.warning("no diff found with any strategy")
    return ""


def parse_changed_files(
    full_diff: str,
    project_dir: Path,
    max_file_size: int,
) -> list[ChangedFile]:
    """Parse unified diff into per-file ChangedFile objects."""
    if not full_diff.strip():
        return []

    file_diffs = _split_diff_by_file(full_diff)

    files: list[ChangedFile] = []
    for file_path, file_diff in file_diffs.items():
        status = _detect_file_status(file_diff, project_dir / file_path)
        content = _read_file_content(project_dir / file_path, max_file_size, status)
        files.append(ChangedFile(path=file_path, status=status, diff=file_diff, content=content))

    return files


def get_commit_messages(project_dir: Path, target_branch: str, base_sha: str | None) -> list[str]:
    """Get commit messages for the MR (from base to HEAD)."""
    ref = base_sha or target_branch
    # %s = subject, %b = body, separated by marker
    fmt = "--format=%s%n%b---END---"
    output = _run_git(project_dir, ["log", f"{ref}...HEAD", fmt, "--reverse"], allow_failure=True)
    if not output:
        output = _run_git(
            project_dir,
            ["log", f"origin/{target_branch}...HEAD", fmt, "--reverse"],
            allow_failure=True,
        )
    if not output:
        return []
    # Parse subject + body blocks separated by ---END---
    raw_commits = output.strip().split("---END---")
    messages = [c.strip() for c in raw_commits if c.strip()]
    logger.info("collected commit messages", count=len(messages))
    return messages


# --- Internal helpers ---


def _split_diff_by_file(full_diff: str) -> dict[str, str]:
    """Split a unified diff into {file_path: diff_chunk} pairs.

    Handles both standard (a/b prefixed) and --no-prefix git diffs.
    """
    chunks: dict[str, str] = {}
    current_file: str | None = None
    current_lines: list[str] = []

    for line in full_diff.splitlines(keepends=True):
        if line.startswith("diff --git "):
            if current_file:
                chunks[current_file] = "".join(current_lines)
            current_file = _parse_diff_header(line)
            current_lines = [line]
        else:
            if current_file is None and line.startswith("+++ "):
                path = line[4:].strip().removeprefix("b/")
                if path != "/dev/null":
                    current_file = path
            current_lines.append(line)

    if current_file:
        chunks[current_file] = "".join(current_lines)

    return chunks


def _parse_diff_header(header_line: str) -> str | None:
    """Extract new filename from a 'diff --git' header line.

    Handles both 'diff --git a/foo b/foo' and 'diff --git foo foo' (noprefix).
    """
    if " b/" in header_line:
        return header_line.split(" b/", 1)[1].strip()
    rest = header_line.removeprefix("diff --git ").strip()
    return rest.split(" ")[-1] if rest else None


def _detect_file_status(file_diff: str, full_path: Path) -> FileStatus:
    """Detect whether a file was added, modified, or deleted from its diff chunk.

    Only checks header lines (first ~10 lines) to avoid false positives
    from code containing '--- /dev/null' as a string.
    """
    for line in file_diff.splitlines()[:10]:
        if line == "--- /dev/null":
            return FileStatus.ADDED
        if line == "+++ /dev/null":
            return FileStatus.DELETED
        if line.startswith("rename from "):
            return FileStatus.RENAMED
    if not full_path.exists():
        return FileStatus.DELETED
    return FileStatus.MODIFIED


def _read_file_content(full_path: Path, max_file_size: int, status: FileStatus) -> str | None:
    """Read file content if it exists and is within size limit."""
    if status == FileStatus.DELETED or not full_path.is_file():
        return None
    try:
        if full_path.stat().st_size > max_file_size:
            return None
        return full_path.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        logger.warning("failed to read file content", path=str(full_path), error=str(e))
        return None


def _run_git(
    project_dir: Path,
    args: list[str],
    allow_failure: bool = False,
) -> str | None:
    """Run a git command and return stdout, or None on failure."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            if not allow_failure:
                logger.warning("git command failed", args=args, stderr=result.stderr[:200])
            return None
        return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning("git command error", args=args, error=str(e))
        return None
