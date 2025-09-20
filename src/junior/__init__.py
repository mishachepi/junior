"""Junior - AI Agent for Code Review."""

__version__ = "0.1.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"

from .config import Settings
from .review_agent import LogicalReviewAgent

__all__ = ["LogicalReviewAgent", "Settings"]