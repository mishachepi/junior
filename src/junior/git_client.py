"""Git client for local repository operations."""

import subprocess
from pathlib import Path
from typing import List, Optional

import git
import structlog

from .models import FileChange, FileStatus

logger = structlog.get_logger(__name__)


class GitClient:
    """Client for local Git operations."""

    def __init__(self, repo_path: Path):
        """Initialize Git client for a repository."""
        self.repo_path = Path(repo_path)
        self.logger = logger.bind(component="GitClient", path=str(repo_path))
        
        try:
            self.repo = git.Repo(self.repo_path)
        except git.exc.InvalidGitRepositoryError:
            raise ValueError(f"Not a git repository: {repo_path}")
        
        if self.repo.bare:
            raise ValueError(f"Cannot work with bare repository: {repo_path}")

    def get_current_branch(self) -> str:
        """Get the current branch name."""
        return self.repo.active_branch.name

    def get_changed_files(self, base_branch: str = "main") -> List[FileChange]:
        """Get files changed between current HEAD and base branch."""
        self.logger.info("Getting changed files", base_branch=base_branch)
        
        try:
            # Get the merge base between current HEAD and base branch
            base_commit = self.repo.commit(base_branch)
            current_commit = self.repo.head.commit
            merge_base = self.repo.merge_base(base_commit, current_commit)[0]
            
            # Get diff between merge base and current commit
            diff = merge_base.diff(current_commit)
            
            files = []
            for item in diff:
                file_change = self._diff_item_to_file_change(item)
                if file_change:
                    files.append(file_change)
            
            self.logger.info("Found changed files", count=len(files))
            return files
            
        except Exception as e:
            self.logger.error("Failed to get changed files", error=str(e))
            raise

    def get_staged_files(self) -> List[FileChange]:
        """Get staged files in the repository."""
        self.logger.info("Getting staged files")
        
        # Get staged changes
        diff = self.repo.index.diff("HEAD", cached=True)
        
        files = []
        for item in diff:
            file_change = self._diff_item_to_file_change(item)
            if file_change:
                files.append(file_change)
        
        self.logger.info("Found staged files", count=len(files))
        return files

    def get_unstaged_files(self) -> List[FileChange]:
        """Get unstaged changes in the repository."""
        self.logger.info("Getting unstaged files")
        
        # Get unstaged changes
        diff = self.repo.index.diff(None)
        
        files = []
        for item in diff:
            file_change = self._diff_item_to_file_change(item)
            if file_change:
                files.append(file_change)
        
        # Also check for untracked files
        for untracked in self.repo.untracked_files:
            file_path = Path(self.repo_path) / untracked
            if file_path.is_file():
                files.append(FileChange(
                    filename=untracked,
                    status=FileStatus.ADDED,
                    additions=len(file_path.read_text().splitlines()),
                    deletions=0,
                    content=file_path.read_text() if self._should_read_content(untracked) else None,
                ))
        
        self.logger.info("Found unstaged files", count=len(files))
        return files

    def _diff_item_to_file_change(self, diff_item) -> Optional[FileChange]:
        """Convert GitPython diff item to FileChange."""
        try:
            # Determine file status
            if diff_item.new_file:
                status = FileStatus.ADDED
                filename = diff_item.b_path
            elif diff_item.deleted_file:
                status = FileStatus.DELETED
                filename = diff_item.a_path
            elif diff_item.renamed_file:
                status = FileStatus.RENAMED
                filename = diff_item.b_path
            else:
                status = FileStatus.MODIFIED
                filename = diff_item.b_path or diff_item.a_path
            
            # Get diff content
            diff_text = None
            try:
                if hasattr(diff_item, 'diff') and diff_item.diff:
                    diff_text = diff_item.diff.decode('utf-8', errors='ignore')
            except Exception:
                pass  # Skip if we can't decode diff
            
            # Count additions/deletions from diff
            additions = 0
            deletions = 0
            if diff_text:
                for line in diff_text.split('\n'):
                    if line.startswith('+') and not line.startswith('+++'):
                        additions += 1
                    elif line.startswith('-') and not line.startswith('---'):
                        deletions += 1
            
            # Get file content for certain types
            content = None
            if status != FileStatus.DELETED and self._should_read_content(filename):
                try:
                    file_path = Path(self.repo_path) / filename
                    if file_path.exists() and file_path.is_file():
                        content = file_path.read_text(encoding='utf-8', errors='ignore')
                except Exception:
                    pass  # Skip if we can't read the file
            
            return FileChange(
                filename=filename,
                status=status,
                additions=additions,
                deletions=deletions,
                diff=diff_text,
                content=content,
            )
            
        except Exception as e:
            self.logger.warning("Failed to process diff item", error=str(e))
            return None

    def _should_read_content(self, filename: str) -> bool:
        """Check if we should read full content for a file."""
        # Only read content for text files under a certain size
        try:
            file_path = Path(self.repo_path) / filename
            if not file_path.exists() or not file_path.is_file():
                return False
            
            # Size check (1MB limit)
            if file_path.stat().st_size > 1024 * 1024:
                return False
            
            # Extension check
            text_extensions = {
                '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.h',
                '.go', '.rs', '.rb', '.php', '.css', '.html', '.xml', '.json',
                '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf', '.sh', '.bash',
                '.sql', '.md', '.txt', '.dockerfile'
            }
            
            ext = file_path.suffix.lower()
            return ext in text_extensions
            
        except Exception:
            return False

    def get_commit_info(self, commit_sha: Optional[str] = None) -> dict:
        """Get information about a specific commit."""
        commit = self.repo.head.commit if commit_sha is None else self.repo.commit(commit_sha)
        
        return {
            "sha": commit.hexsha,
            "message": commit.message,
            "author": {
                "name": commit.author.name,
                "email": commit.author.email,
            },
            "committer": {
                "name": commit.committer.name,
                "email": commit.committer.email,
            },
            "authored_date": commit.authored_datetime,
            "committed_date": commit.committed_datetime,
            "parents": [p.hexsha for p in commit.parents],
        }

    def is_clean(self) -> bool:
        """Check if the working directory is clean."""
        return not self.repo.is_dirty() and not self.repo.untracked_files

    def get_remote_url(self, remote_name: str = "origin") -> Optional[str]:
        """Get the URL of a remote."""
        try:
            remote = self.repo.remote(remote_name)
            return list(remote.urls)[0]
        except Exception:
            return None

    def get_branches(self) -> dict:
        """Get all branches."""
        return {
            "local": [branch.name for branch in self.repo.branches],
            "remote": [ref.name for ref in self.repo.remote().refs],
            "current": self.get_current_branch(),
        }