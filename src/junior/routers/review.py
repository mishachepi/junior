"""Manual review endpoints."""

import structlog
from fastapi import APIRouter, HTTPException, status

from ..config import settings
from ..models import ReviewData
from ..services import GitHubService, ReviewService

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/review", tags=["review"])


@router.post("")
async def manual_review(request: dict):
    """Manual review endpoint for testing."""
    if not settings.debug:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Endpoint not available in production",
        )

    try:
        repository = request["repository"]
        pr_number = request["pr_number"]

        # Extract minimal review data
        review_data = ReviewData(
            repository=repository,
            pr_number=pr_number,
            title=request.get("title", "Manual Review"),
            description=request.get("description", ""),
            author=request.get("author", "manual"),
            base_branch=request.get("base_branch", "main"),
            head_branch=request.get("head_branch", "feature"),
            base_sha=request.get("base_sha", ""),
            head_sha=request.get("head_sha", ""),
            diff_url=request.get("diff_url", ""),
            clone_url=request.get("clone_url", ""),
        )

        # Get diff content if not provided
        diff_content = request.get("diff_content", "")
        if not diff_content:
            github_service = GitHubService()
            diff_content = await github_service.get_pr_diff(repository, pr_number)

        # Perform review with optional pre-fetched data
        review_service = ReviewService()
        review_result = await review_service.manual_review(
            review_data=review_data,
            diff_content=diff_content,
            file_contents=request.get("file_contents", {}),
            project_structure=request.get("project_structure", {}),
        )

        return review_result

    except KeyError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required field: {e}",
        ) from e
    except Exception as e:
        logger.error("Manual review failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        ) from e
