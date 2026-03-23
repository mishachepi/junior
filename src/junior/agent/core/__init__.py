"""Core utilities shared across all agent backends."""

from junior.agent.core.context_builder import build_user_message
from junior.agent.core.instructions import read_project_instructions

__all__ = ["build_user_message", "read_project_instructions"]
