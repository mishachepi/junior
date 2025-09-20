"""Data models for Junior."""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class FileStatus(str, Enum):
    """File status in a pull request."""
    
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


class Severity(str, Enum):
    """Issue severity levels."""
    
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReviewCategory(str, Enum):
    """Review comment categories."""
    
    SECURITY = "security"
    PERFORMANCE = "performance"
    STYLE = "style"
    COMPLEXITY = "complexity"
    LOGIC = "logic"
    DOCUMENTATION = "documentation"
    TESTING = "testing"
    CRITICAL_BUG = "critical_bug"
    NAMING = "naming"
    OPTIMIZATION = "optimization"
    DRY_VIOLATION = "dry_violation"
    KISS_VIOLATION = "kiss_violation"


class FileChange(BaseModel):
    """Represents a file change in a pull request."""
    
    filename: str = Field(..., description="Path to the file")
    status: FileStatus = Field(..., description="Status of the file change")
    additions: int = Field(0, description="Number of lines added")
    deletions: int = Field(0, description="Number of lines deleted")
    diff: Optional[str] = Field(None, description="Diff content")
    content: Optional[str] = Field(None, description="Full file content")


class ReviewComment(BaseModel):
    """Represents a code review comment."""
    
    category: ReviewCategory = Field(..., description="Category of the comment")
    message: str = Field(..., description="Comment message")
    filename: Optional[str] = Field(None, description="File the comment relates to")
    line_number: Optional[int] = Field(None, description="Line number the comment relates to")
    severity: Severity = Field(Severity.MEDIUM, description="Severity of the issue")
    suggestion: Optional[str] = Field(None, description="Suggested fix or improvement")
    rule: Optional[str] = Field(None, description="Rule or principle violated")


class CodeReviewRequest(BaseModel):
    """Request for code review."""
    
    repository: str = Field(..., description="Repository name (owner/repo)")
    pr_number: int = Field(..., description="Pull request number")
    title: str = Field(..., description="Pull request title")
    description: Optional[str] = Field(None, description="Pull request description")
    author: str = Field(..., description="Pull request author")
    base_branch: str = Field("main", description="Base branch")
    head_branch: str = Field(..., description="Head branch")
    files: List[FileChange] = Field(..., description="List of changed files")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CodeReviewResult(BaseModel):
    """Result of code review."""
    
    pr_number: int = Field(..., description="Pull request number")
    repository: str = Field(..., description="Repository name")
    comments: List[ReviewComment] = Field(..., description="Review comments")
    summary: str = Field(..., description="Overall review summary")
    approved: bool = Field(False, description="Whether the PR is approved")
    
    # Issue counts by category
    security_issues_count: int = Field(0, description="Number of security issues")
    performance_issues_count: int = Field(0, description="Number of performance issues")
    style_issues_count: int = Field(0, description="Number of style issues")
    complexity_issues_count: int = Field(0, description="Number of complexity issues")
    
    reviewed_at: datetime = Field(default_factory=datetime.utcnow)
    
    @property
    def total_issues(self) -> int:
        """Total number of issues found."""
        return len(self.comments)
    
    @property
    def critical_issues(self) -> List[ReviewComment]:
        """Get critical issues."""
        return [c for c in self.comments if c.severity == Severity.CRITICAL]
    
    @property
    def high_issues(self) -> List[ReviewComment]:
        """Get high severity issues."""
        return [c for c in self.comments if c.severity == Severity.HIGH]


class WebhookPayload(BaseModel):
    """GitHub webhook payload for pull requests."""
    
    action: str = Field(..., description="Webhook action")
    pull_request: dict = Field(..., description="Pull request data")
    repository: dict = Field(..., description="Repository data")


class ReviewStatus(str, Enum):
    """Review status options."""
    
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ReviewJob(BaseModel):
    """Represents a review job in the queue."""
    
    id: str = Field(..., description="Unique job ID")
    repository: str = Field(..., description="Repository name")
    pr_number: int = Field(..., description="Pull request number")
    status: ReviewStatus = Field(ReviewStatus.PENDING, description="Job status")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = Field(None, description="When the job started")
    completed_at: Optional[datetime] = Field(None, description="When the job completed")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    result: Optional[CodeReviewResult] = Field(None, description="Review result")


class RepositoryAnalysis(BaseModel):
    """Repository analysis results."""
    
    project_type: str = Field(..., description="Type of project (python, nodejs, etc.)")
    main_language: str = Field(..., description="Primary programming language")
    frameworks: List[str] = Field(default_factory=list, description="Detected frameworks")
    dependencies: Dict[str, List[str]] = Field(default_factory=dict, description="Project dependencies")
    directory_structure: Dict = Field(default_factory=dict, description="Directory structure")
    config_files: List[str] = Field(default_factory=list, description="Configuration files")
    test_directories: List[str] = Field(default_factory=list, description="Test directories")
    total_files_analyzed: int = Field(0, description="Number of files analyzed")
    changed_files_count: int = Field(0, description="Number of changed files")


class LogicalReviewRequest(BaseModel):
    """Request for logical code review."""
    
    repository: str = Field(..., description="Repository name")
    pr_number: int = Field(..., description="Pull request number")
    diff_content: str = Field(..., description="Git diff content")
    file_contents: Dict[str, str] = Field(default_factory=dict, description="File contents")
    project_structure: RepositoryAnalysis = Field(..., description="Project structure analysis")
    focus_areas: List[str] = Field(
        default=["logic", "security", "critical_bugs", "naming", "optimization", "principles"],
        description="Areas to focus review on"
    )


class LogicalReviewResult(BaseModel):
    """Result of logical code review."""
    
    repository: str = Field(..., description="Repository name")
    pr_number: int = Field(..., description="Pull request number")
    findings: List[Dict] = Field(default_factory=list, description="Raw findings from review")
    summary: str = Field(..., description="Review summary")
    recommendation: Literal["approve", "request_changes", "comment"] = Field(..., description="Review recommendation")
    comments: List[ReviewComment] = Field(default_factory=list, description="Structured review comments")
    
    # Counts by severity
    critical_count: int = Field(0, description="Number of critical issues")
    high_count: int = Field(0, description="Number of high severity issues") 
    medium_count: int = Field(0, description="Number of medium severity issues")
    low_count: int = Field(0, description="Number of low severity issues")
    total_findings: int = Field(0, description="Total number of findings")
    
    # Counts by category
    logic_issues: int = Field(0, description="Logic-related issues")
    security_issues: int = Field(0, description="Security-related issues")
    critical_bugs: int = Field(0, description="Critical bugs found")
    naming_issues: int = Field(0, description="Naming convention issues")
    optimization_opportunities: int = Field(0, description="Optimization opportunities")
    principle_violations: int = Field(0, description="Design principle violations")
    
    reviewed_at: datetime = Field(default_factory=datetime.utcnow)
    processing_time_ms: Optional[int] = Field(None, description="Processing time in milliseconds")
    error: Optional[str] = Field(None, description="Error message if review failed")