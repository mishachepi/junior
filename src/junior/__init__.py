"""Junior - AI Agent for Code Review."""

__version__ = "0.1.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"

from .agent import ReviewAgent
from .app import app
from .config import Settings
from .models import ReviewCategory, ReviewData, Severity
from .services import GitHubService, RepositoryService, ReviewService

__all__ = [
    "ReviewAgent",
    "Settings",
    "ReviewService",
    "GitHubService",
    "RepositoryService",
    "ReviewData",
    "ReviewCategory",
    "Severity",
    "app",
]
