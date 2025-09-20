"""GitHub API client for Junior."""

from typing import Dict, List, Optional

import structlog
from github import Github
from github.PullRequest import PullRequest

from .config import settings
from .models import FileChange, FileStatus

logger = structlog.get_logger(__name__)


class GitHubClient:
    """Client for interacting with GitHub API."""

    def __init__(self, token: Optional[str] = None):
        """Initialize GitHub client."""
        self.token = token or settings.github_token
        if not self.token:
            raise ValueError("GitHub token is required")
        
        self.github = Github(self.token)
        self.logger = logger.bind(component="GitHubClient")

    async def get_authenticated_user(self) -> Dict:
        """Get authenticated user information."""
        try:
            user = self.github.get_user()
            return {
                "login": user.login,
                "name": user.name or user.login,
                "email": user.email,
                "id": user.id,
            }
        except Exception as e:
            self.logger.error("Failed to get authenticated user", error=str(e))
            raise

    async def get_pull_request(self, repository: str, pr_number: int) -> Dict:
        """Get pull request information."""
        self.logger.info("Fetching pull request", repo=repository, pr=pr_number)
        
        repo = self.github.get_repo(repository)
        pr = repo.get_pull(pr_number)
        
        return {
            "number": pr.number,
            "title": pr.title,
            "body": pr.body,
            "state": pr.state,
            "user": {
                "login": pr.user.login,
                "id": pr.user.id,
            },
            "base": {
                "ref": pr.base.ref,
                "sha": pr.base.sha,
            },
            "head": {
                "ref": pr.head.ref,
                "sha": pr.head.sha,
            },
            "created_at": pr.created_at,
            "updated_at": pr.updated_at,
            "merged": pr.merged,
            "mergeable": pr.mergeable,
            "additions": pr.additions,
            "deletions": pr.deletions,
            "changed_files": pr.changed_files,
            # Add diff_url for fetching
            "diff_url": f"https://api.github.com/repos/{repository}/pulls/{pr_number}.diff",
            "patch_url": f"https://api.github.com/repos/{repository}/pulls/{pr_number}.patch",
            "html_url": pr.html_url,
        }

    async def get_pr_files(self, repository: str, pr_number: int) -> List[FileChange]:
        """Get files changed in a pull request."""
        self.logger.info("Fetching PR files", repo=repository, pr=pr_number)
        
        repo = self.github.get_repo(repository)
        pr = repo.get_pull(pr_number)
        
        files = []
        for file in pr.get_files():
            # Map GitHub file status to our enum
            status_map = {
                "added": FileStatus.ADDED,
                "modified": FileStatus.MODIFIED,
                "removed": FileStatus.DELETED,
                "renamed": FileStatus.RENAMED,
            }
            
            file_change = FileChange(
                filename=file.filename,
                status=status_map.get(file.status, FileStatus.MODIFIED),
                additions=file.additions,
                deletions=file.deletions,
                diff=file.patch,
            )
            
            # Get file content for certain file types
            if file.status != "removed" and self._should_get_content(file.filename):
                try:
                    content = repo.get_contents(file.filename, ref=pr.head.sha)
                    if hasattr(content, 'decoded_content'):
                        file_change.content = content.decoded_content.decode('utf-8')
                except Exception as e:
                    self.logger.warning("Failed to get file content", 
                                      filename=file.filename, error=str(e))
            
            files.append(file_change)
        
        self.logger.info("Fetched PR files", count=len(files))
        return files

    async def post_review_comment(
        self, 
        repository: str, 
        pr_number: int, 
        body: str,
        commit_sha: Optional[str] = None,
        path: Optional[str] = None,
        line: Optional[int] = None,
    ) -> Dict:
        """Post a review comment on a pull request."""
        self.logger.info("Posting review comment", repo=repository, pr=pr_number)
        
        repo = self.github.get_repo(repository)
        pr = repo.get_pull(pr_number)
        
        if path and line and commit_sha:
            # Line-specific comment
            comment = pr.create_review_comment(
                body=body,
                commit=repo.get_commit(commit_sha),
                path=path,
                line=line,
            )
        else:
            # General PR comment
            comment = pr.create_issue_comment(body)
        
        return {
            "id": comment.id,
            "body": comment.body,
            "created_at": comment.created_at,
        }

    async def submit_review(
        self, 
        repository: str, 
        pr_number: int, 
        event: str,  # "APPROVE", "REQUEST_CHANGES", "COMMENT"
        body: Optional[str] = None,
        comments: Optional[List[Dict]] = None,
    ) -> Dict:
        """Submit a complete review for a pull request."""
        self.logger.info("Submitting review", repo=repository, pr=pr_number, event=event)
        
        try:
            repo = self.github.get_repo(repository)
            pr = repo.get_pull(pr_number)
            
            # Get the latest commit SHA for the review
            commit_sha = pr.head.sha
            
            # Prepare review comments with commit SHA
            review_comments = []
            if comments:
                for comment in comments:
                    if all(k in comment for k in ["path", "line", "body"]):
                        review_comments.append({
                            "path": comment["path"],
                            "line": comment["line"],
                            "body": comment["body"],
                        })
            
            # Submit review with commit SHA
            if review_comments:
                # Submit review with inline comments
                review = pr.create_review(
                    body=body,
                    event=event,
                    commit=repo.get_commit(commit_sha),
                    comments=review_comments,
                )
            else:
                # Submit review without inline comments
                review = pr.create_review(
                    body=body,
                    event=event,
                )
            
            self.logger.info("Review submitted successfully", 
                           review_id=review.id, 
                           comments_count=len(review_comments))
            
            return {
                "id": review.id,
                "state": review.state,
                "body": review.body,
                "submitted_at": review.submitted_at,
                "commit_sha": commit_sha,
                "comments_count": len(review_comments),
            }
            
        except Exception as e:
            self.logger.error("Failed to submit review", 
                            repo=repository, 
                            pr=pr_number, 
                            error=str(e))
            raise

    async def check_permissions(self, repository: str) -> Dict[str, bool]:
        """Check user permissions for a repository."""
        try:
            repo = self.github.get_repo(repository)
            permissions = repo.get_collaborator_permission(self.github.get_user())
            
            return {
                "read": permissions in ["read", "write", "admin"],
                "write": permissions in ["write", "admin"],
                "admin": permissions == "admin",
            }
        except Exception as e:
            self.logger.error("Failed to check permissions", repo=repository, error=str(e))
            return {"read": False, "write": False, "admin": False}

    def _should_get_content(self, filename: str) -> bool:
        """Check if we should fetch full content for a file."""
        # Only fetch content for certain file types and sizes
        text_extensions = {
            '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.h',
            '.go', '.rs', '.rb', '.php', '.css', '.html', '.xml', '.json',
            '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf', '.sh', '.bash',
            '.sql', '.md', '.txt', '.dockerfile'
        }
        
        ext = '.' + filename.split('.')[-1].lower() if '.' in filename else ''
        return ext in text_extensions

    async def get_repository_info(self, repository: str) -> Dict:
        """Get repository information."""
        repo = self.github.get_repo(repository)
        
        return {
            "name": repo.name,
            "full_name": repo.full_name,
            "description": repo.description,
            "private": repo.private,
            "default_branch": repo.default_branch,
            "language": repo.language,
            "languages": dict(repo.get_languages()),
            "size": repo.size,
            "stargazers_count": repo.stargazers_count,
            "forks_count": repo.forks_count,
            "open_issues_count": repo.open_issues_count,
        }