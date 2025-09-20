"""API routers for Junior."""

from .health import router as health_router
from .review import router as review_router
from .webhook import router as webhook_router

__all__ = ["health_router", "webhook_router", "review_router"]
