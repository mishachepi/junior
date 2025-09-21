"""Review by repo and PR number endpoints."""

import structlog
from fastapi import APIRouter, HTTPException, status

from ..config import settings
from ..models import ReviewData
from ..services import GitHubService, ReviewService

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/review", tags=["review"])


@router.post("")
async def do_review_by_repo_and_pr(request: dict):
    """Review by repo and PR number endpoint for testing."""
    if not settings.debug:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Endpoint not available in production",
        )

    try:
        repository = request["repository"]
        pr_number = request["pr_number"]

        # Fetch PR data from GitHub if other parameters are missing
        github_service = GitHubService()

        # Check if we need to fetch PR data
        missing_params = not all([
            request.get("title"),
            request.get("base_branch"),
            request.get("head_branch"),
            request.get("base_sha"),
            request.get("head_sha")
        ])

        if missing_params:
            github_client = github_service._get_client()
            pr_data = await github_client.get_pull_request(repository, pr_number)

            # Use fetched data to fill missing parameters
            title = request.get("title", pr_data.get("title", "Review"))
            description = request.get("description", pr_data.get("body", ""))
            author = request.get("author", pr_data.get("user", {}).get("login", "manual"))
            base_branch = request.get("base_branch", pr_data.get("base", {}).get("ref", "main"))
            head_branch = request.get("head_branch", pr_data.get("head", {}).get("ref", "feature"))
            base_sha = request.get("base_sha", pr_data.get("base", {}).get("sha", ""))
            head_sha = request.get("head_sha", pr_data.get("head", {}).get("sha", ""))
            diff_url = request.get("diff_url", pr_data.get("diff_url", ""))
            clone_url = request.get("clone_url", f"https://github.com/{repository}.git")
        else:
            # Use provided or default values
            title = request.get("title", "Review")
            description = request.get("description", "")
            author = request.get("author", "manual")
            base_branch = request.get("base_branch", "main")
            head_branch = request.get("head_branch", "feature")
            base_sha = request.get("base_sha", "")
            head_sha = request.get("head_sha", "")
            diff_url = request.get("diff_url", "")
            clone_url = request.get("clone_url", "")

        # Create review data with computed/fetched parameters
        review_data = ReviewData(
            repository=repository,
            pr_number=pr_number,
            title=title,
            description=description,
            author=author,
            base_branch=base_branch,
            head_branch=head_branch,
            base_sha=base_sha,
            head_sha=head_sha,
            diff_url=diff_url,
            clone_url=clone_url,
        )

        # Get diff content if not provided
        diff_content = request.get("diff_content", "")
        if not diff_content:
            diff_content = await github_service.get_pr_diff(repository, pr_number)

        # Perform review with optional pre-fetched data
        review_service = ReviewService()
        review_result = await review_service.do_review_by_repo_and_pr(
            review_data=review_data,
            diff_content=diff_content,
            file_contents=request.get("file_contents", {}),
            project_structure=request.get("project_structure", {}),
        )

        # Log the review result before posting
        logger.info(
            "Review result to be posted",
            repo=review_data.repository,
            pr=review_data.pr_number,
            total_findings=review_result.get("total_findings", 0),
            has_findings_details="findings" in review_result,
            findings_count=len(review_result.get("findings", [])),
        )

        logger.debug(
            "Full review result",
            review_result=review_result,
        )

        # Post review to GitHub
        await github_service.post_review_to_github(
            review_data.repository, review_data.pr_number, review_result
        )

        return review_result

    except KeyError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required field: {e}",
        ) from e
    except Exception as e:
        logger.error("Review by repo and PR number failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        ) from e
