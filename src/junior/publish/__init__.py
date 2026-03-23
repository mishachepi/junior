"""Phase 3: Publish review results — backend dispatch."""

import importlib

from junior.config import Settings
from junior.models import ReviewResult


def publish(settings: Settings, result: ReviewResult) -> None:
    """Post review results using the configured publisher backend.

    Dispatches to publisher module based on settings.resolved_publisher enum value.
    Each backend module must export: post_review(settings, result)
    """
    module = importlib.import_module(settings.resolved_publisher.value)
    module.post_review(settings, result)
