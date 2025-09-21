"""Review processing service."""

import json
from datetime import datetime

import structlog

from ..agent import ReviewAgent
from ..config import settings
from ..models import ReviewData

logger = structlog.get_logger(__name__)


class ReviewService:
    """Service for handling code review operations."""

    def __init__(self):
        self.logger = logger.bind(component="ReviewService")

    async def process_pr_review(self, review_data: ReviewData) -> dict:
        """Process PR review with minimal data."""
        repository = review_data.repository
        pr_number = review_data.pr_number

        self.logger.info("Starting PR review", repo=repository, pr=pr_number)

        try:
            # Perform AI review with minimal data - agent will fetch additional data on demand
            review_agent = ReviewAgent()

            # Save minimal review data for debugging
            if settings.debug:
                timestamp = datetime.now().timestamp()
                with open(f"./review_data_{timestamp}.json", "w") as f:
                    json.dump(review_data.model_dump(), f, indent=4)

            # Review agent will fetch diff, file contents, and project structure on demand via MCP
            review_result = await review_agent.review_pull_request(
                review_data=review_data
            )
            print("Review result:", review_result)

            self.logger.info(
                "PR review completed",
                repo=repository,
                pr=pr_number,
                findings=review_result["total_findings"],
            )

            return review_result

        except Exception as e:
            self.logger.error(
                "PR review failed", repo=repository, pr=pr_number, error=str(e)
            )
            raise

    async def do_review_by_repo_and_pr(
        self,
        review_data: ReviewData,
        diff_content: str = "",
        file_contents: dict[str, str] | None = None,
        project_structure: dict | None = None,
    ) -> dict:
        """Perform Review by repo and PR number with optional pre-fetched data."""
        self.logger.info(
            "Starting Review by repo and PR number",
            repo=review_data.repository,
            pr=review_data.pr_number,
        )

        try:
            review_agent = ReviewAgent()
            review_result = await review_agent.review_pull_request(
                review_data=review_data,
                diff_content=diff_content,
                file_contents=file_contents or {},
                project_structure=project_structure or {},
            )

            self.logger.info(
                "Review by repo and PR number completed",
                repo=review_data.repository,
                pr=review_data.pr_number,
                findings=review_result["total_findings"],
            )

            return review_result

        except Exception as e:
            self.logger.error(
                "Review by repo and PR number failed",
                repo=review_data.repository,
                pr=review_data.pr_number,
                error=str(e),
            )
            raise
