"""FastAPI application for Junior webhook service."""

import asyncio
import json
from datetime import datetime
from typing import Dict, Optional

import structlog
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .github_client import GitHubClient
from .mcp_tools import MCPRepositoryAnalyzer
from .review_agent import LogicalReviewAgent
from .webhook import PullRequestWebhookPayload, WebhookProcessor

# Configure logging
import logging

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer() if settings.debug else structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        getattr(logging, settings.log_level.upper())
    ),
    logger_factory=structlog.WriteLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

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

# Initialize services (lazy-loaded to avoid config issues)
webhook_processor = WebhookProcessor()

def get_github_client():
    """Get GitHub client instance."""
    if not settings.github_token:
        raise ValueError("GitHub token is required")
    return GitHubClient()

def get_review_agent():
    """Get review agent instance."""
    return LogicalReviewAgent()

def get_mcp_analyzer():
    """Get MCP analyzer instance.""" 
    return MCPRepositoryAnalyzer()


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "junior-webhook"}


@app.get("/ready")
async def readiness_check():
    """Readiness check endpoint."""
    try:
        # Quick check of dependencies
        await get_github_client().get_authenticated_user()
        return {"status": "ready", "service": "junior-webhook"}
    except Exception as e:
        logger.error("Readiness check failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not ready"
        )


@app.post("/webhook/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """Handle GitHub webhook events."""
    try:
        # Get raw payload for signature verification
        payload_bytes = await request.body()
        
        # Verify webhook signature
        if not await webhook_processor.verify_signature(request, payload_bytes):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature"
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
        
        # Extract review data
        review_data = webhook_processor.extract_review_data(webhook_payload)
        review_data["webhook_received_at"] = datetime.utcnow().isoformat()
        
        # Process review in background
        background_tasks.add_task(process_pr_review, review_data)
        
        return {
            "message": "PR review queued",
            "repository": review_data["repository"],
            "pr_number": review_data["pr_number"],
            "action": webhook_payload.action
        }
        
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )
    except Exception as e:
        logger.error("Webhook processing failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


async def process_pr_review(review_data: Dict):
    """Process PR review in background."""
    repository = review_data["repository"]
    pr_number = review_data["pr_number"]
    
    logger.info("Starting PR review", repo=repository, pr=pr_number)
    
    try:
        # Step 1: Get diff content
        diff_content = await get_pr_diff(repository, pr_number)
        
        # Step 2: Get file contents and project structure
        file_contents, project_structure = await analyze_repository(
            repository, 
            review_data["head_sha"],
            review_data["base_sha"]
        )
        
        # Step 3: Perform AI review
        review_agent = get_review_agent()
        review_result = await review_agent.review_pull_request(
            review_data=review_data,
            diff_content=diff_content,
            file_contents=file_contents,
            project_structure=project_structure
        )
        
        # Step 4: Post review to GitHub
        await post_review_to_github(repository, pr_number, review_result)
        
        logger.info("PR review completed", 
                   repo=repository, 
                   pr=pr_number,
                   findings=review_result["total_findings"])
        
    except Exception as e:
        logger.error("PR review failed", 
                    repo=repository, 
                    pr=pr_number, 
                    error=str(e))
        
        # Post error comment to PR
        try:
            github_client = get_github_client()
            await github_client.post_review_comment(
                repository, 
                pr_number,
                f"❌ **Junior Review Failed**\n\nI encountered an error while reviewing this PR: {str(e)}\n\nPlease check the service logs for more details."
            )
        except Exception as comment_error:
            logger.error("Failed to post error comment", error=str(comment_error))


async def get_pr_diff(repository: str, pr_number: int) -> str:
    """Get the diff content for a PR."""
    try:
        # Get PR data
        github_client = get_github_client()
        pr_data = await github_client.get_pull_request(repository, pr_number)
        
        # Fetch diff content with proper authentication
        import httpx
        headers = {
            "Accept": "application/vnd.github.v3.diff",
            "User-Agent": "Junior-AI-Review-Agent/1.0"
        }
        
        # Add GitHub token for authentication
        if settings.github_token:
            headers["Authorization"] = f"token {settings.github_token}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Use the PR's diff URL from GitHub API
            diff_url = pr_data.get("diff_url") or f"https://api.github.com/repos/{repository}/pulls/{pr_number}.diff"
            
            response = await client.get(diff_url, headers=headers)
            response.raise_for_status()
            return response.text
            
    except Exception as e:
        logger.error("Failed to get PR diff", repo=repository, pr=pr_number, error=str(e))
        raise


async def analyze_repository(repository: str, head_sha: str, base_sha: str) -> tuple[Dict[str, str], Dict]:
    """Analyze repository structure and get relevant file contents."""
    try:
        # Use MCP tools to analyze repository
        mcp_analyzer = get_mcp_analyzer()
        analysis_result = await mcp_analyzer.analyze_repository(
            repository=repository,
            head_sha=head_sha,
            base_sha=base_sha
        )
        
        return analysis_result["file_contents"], analysis_result["project_structure"]
        
    except Exception as e:
        logger.error("Repository analysis failed", repo=repository, error=str(e))
        # Return empty analysis if MCP fails
        return {}, {}


async def post_review_to_github(repository: str, pr_number: int, review_result: Dict):
    """Post review results to GitHub."""
    try:
        # Determine review event
        recommendation = review_result.get("recommendation", "comment")
        
        github_event_map = {
            "approve": "APPROVE",
            "request_changes": "REQUEST_CHANGES", 
            "comment": "COMMENT"
        }
        
        event = github_event_map.get(recommendation, "COMMENT")
        
        # Format review summary
        summary = format_review_summary(review_result)
        
        # Prepare inline comments
        inline_comments = []
        for comment in review_result.get("comments", []):
            if comment.get("filename") and comment.get("line_number"):
                inline_comments.append({
                    "path": comment["filename"],
                    "line": comment["line_number"],
                    "body": f"**{comment['severity'].upper()}**: {comment['message']}" + 
                           (f"\n\n💡 **Suggestion**: {comment['suggestion']}" if comment.get('suggestion') else "")
                })
        
        # Submit review
        github_client = get_github_client()
        await github_client.submit_review(
            repository=repository,
            pr_number=pr_number,
            event=event,
            body=summary,
            comments=inline_comments[:20]  # Limit to 20 inline comments
        )
        
        logger.info("Review posted to GitHub", 
                   repo=repository, 
                   pr=pr_number, 
                   event=event,
                   inline_comments=len(inline_comments))
        
    except Exception as e:
        logger.error("Failed to post review", repo=repository, pr=pr_number, error=str(e))
        raise


def format_review_summary(review_result: Dict) -> str:
    """Format review results into a GitHub comment."""
    summary = review_result.get("summary", "Review completed")
    
    # Add findings summary
    total = review_result.get("total_findings", 0)
    critical = review_result.get("critical_count", 0)
    high = review_result.get("high_count", 0)
    medium = review_result.get("medium_count", 0)
    low = review_result.get("low_count", 0)
    
    if total == 0:
        findings_summary = "✅ No issues found! Great work!"
    else:
        findings_summary = f"📊 **Findings Summary**: {total} total"
        if critical > 0:
            findings_summary += f" • 🔴 {critical} critical"
        if high > 0:
            findings_summary += f" • 🟠 {high} high"
        if medium > 0:
            findings_summary += f" • 🟡 {medium} medium"
        if low > 0:
            findings_summary += f" • 🟢 {low} low"
    
    # Format final comment
    formatted_summary = f"""## 🤖 Junior Code Review

{summary}

{findings_summary}

---
*Reviewed by [Junior AI Agent](https://github.com/yourusername/junior) - Focusing on logic, security, and code quality*
"""
    
    return formatted_summary


@app.post("/review")
async def manual_review(request: Dict):
    """Manual review endpoint for testing."""
    if not settings.debug:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Endpoint not available in production"
        )
    
    try:
        repository = request["repository"]
        pr_number = request["pr_number"]
        
        # Extract review data
        review_data = {
            "repository": repository,
            "pr_number": pr_number,
            "title": request.get("title", "Manual Review"),
            "description": request.get("description", ""),
            "author": request.get("author", "manual"),
            "base_branch": request.get("base_branch", "main"),
            "head_branch": request.get("head_branch", "feature"),
        }
        
        # Get diff content
        diff_content = request.get("diff_content", "")
        if not diff_content:
            diff_content = await get_pr_diff(repository, pr_number)
        
        # Perform review
        review_agent = get_review_agent()
        review_result = await review_agent.review_pull_request(
            review_data=review_data,
            diff_content=diff_content,
            file_contents=request.get("file_contents", {}),
            project_structure=request.get("project_structure", {})
        )
        
        return review_result
        
    except Exception as e:
        logger.error("Manual review failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "junior.api:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )