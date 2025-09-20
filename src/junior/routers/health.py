"""Health check endpoints."""

import structlog
from fastapi import APIRouter, HTTPException, status

from ..services import GitHubService

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "junior-webhook"}


@router.get("/ready")
async def readiness_check():
    """Readiness check endpoint."""
    try:
        # Quick check of dependencies
        github_service = GitHubService()
        await github_service.get_authenticated_user()
        return {"status": "ready", "service": "junior-webhook"}
    except Exception as e:
        logger.error("Readiness check failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Service not ready"
        ) from e
