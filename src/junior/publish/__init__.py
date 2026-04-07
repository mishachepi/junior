"""Phase 3: Publish review results — backend dispatch."""

from junior.config import PublishBackend, Settings
from junior.models import ReviewResult
from junior.publish.github import post_review as _post_review_github
from junior.publish.gitlab import post_review as _post_review_gitlab

_PUBLISHERS = {
    PublishBackend.GITHUB: _post_review_github,
    PublishBackend.GITLAB: _post_review_gitlab,
}


def publish(settings: Settings, result: ReviewResult) -> None:
    """Post review results using the configured publisher backend.

    Dispatches to publisher module based on settings.resolved_publisher enum value.
    Each backend module must export: post_review(settings, result)
    """
    _PUBLISHERS[settings.resolved_publisher](settings, result)
