"""Webhook endpoints."""

import json

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status

from ..models import ReviewData
from ..services import (
    GitHubService,
    ReviewService,
    PullRequestWebhookPayload,
    WebhookProcessor,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/webhook", tags=["webhook"])

# Initialize services
webhook_processor = WebhookProcessor()


@router.post("/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """Handle GitHub webhook events."""
    try:
        # Get raw payload for signature verification
        payload_bytes = await request.body()

        # Verify webhook signature
        if not await webhook_processor.verify_signature(request, payload_bytes):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature",
            )

        # Parse payload
        payload_json = json.loads(payload_bytes.decode("utf-8"))

        # Check if it's a pull request event
        if "pull_request" not in payload_json:
            return {"message": "Not a pull request event, ignoring"}

        # Validate payload structure
        webhook_payload = PullRequestWebhookPayload(**payload_json)

        # Check if we should process this event
        if not webhook_processor.should_process_event(webhook_payload):
            return {"message": f"Skipping action: {webhook_payload.action}"}

        # Extract minimal review data
        review_data_dict = webhook_processor.extract_minimal_review_data(
            webhook_payload
        )
        review_data = ReviewData(**review_data_dict)

        # Process review in background
        background_tasks.add_task(_process_webhook_review, review_data)

        return {
            "message": "PR review queued",
            "repository": review_data.repository,
            "pr_number": review_data.pr_number,
            "action": webhook_payload.action,
        }

    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload"
        ) from e
    except Exception as e:
        logger.error("Webhook processing failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from e


async def _process_webhook_review(review_data: ReviewData):
    """Process PR review in background task."""
    review_service = ReviewService()
    github_service = GitHubService()

    try:
        # Process the review
        review_result = await review_service.process_pr_review(review_data)

        # Post review to GitHub
        await github_service.post_review_to_github(
            review_data.repository, review_data.pr_number, review_result
        )

    except Exception as e:
        logger.error(
            "Background review processing failed",
            repo=review_data.repository,
            pr=review_data.pr_number,
            error=str(e),
        )

        # Post error comment to PR
        await github_service.post_error_comment(
            review_data.repository, review_data.pr_number, str(e)
        )
