"""FastAPI application factory for Junior webhook service."""

import logging

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import health_router, review_router, webhook_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    # Configure logging
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer()
            if settings.debug
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper())
        ),
        logger_factory=structlog.WriteLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Initialize FastAPI app
    app = FastAPI(
        title="Junior - AI Code Review Agent",
        description="Webhook-based AI agent for comprehensive code review",
        version="0.1.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.debug else [],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(health_router)
    app.include_router(webhook_router)
    app.include_router(review_router)

    return app


# Create the app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    # Check if we should enable reload (for development)
    reload = settings.debug

    # If running with debugger or in development, force reload
    import sys

    if any("debug" in arg.lower() for arg in sys.argv) or settings.debug:
        reload = True

    print("🚀 Starting Junior API server...")
    print(f"   Mode: {'DEBUG' if settings.debug else 'PRODUCTION'}")
    print(f"   Host: {settings.api_host}")
    print(f"   Port: {settings.api_port}")
    print(f"   Reload: {reload}")
    print(f"   Docs: {'http://127.0.0.1:8000/docs' if settings.debug else 'Disabled'}")
    print("   Health: http://127.0.0.1:8000/health")

    uvicorn.run(
        "junior.app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=reload,
        log_level=settings.log_level.lower(),
    )
