"""Shared utilities and models for code review functionality."""

import structlog
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel

from ..config import settings
from ..models import ReviewData

logger = structlog.get_logger(__name__)


class ReviewFinding(BaseModel):
    """A single review finding."""

    category: str
    severity: str
    message: str
    file_path: str | None = None
    line_number: int | None = None
    suggestion: str | None = None
    principle_violated: str | None = None


class ReviewFindings(BaseModel):
    """Collection of review findings."""

    findings: list[ReviewFinding]
    summary: str
    overall_recommendation: str  # "approve", "request_changes", "comment"


class ReviewState(BaseModel):
    """State for review workflow."""

    review_data: ReviewData
    diff_content: str = ""
    file_contents: dict[str, str] = {}
    project_structure: dict = {}
    findings: list[ReviewFinding] = []
    current_step: str = "start"
    error: str | None = None
    mcp_analyzer: object | None = None  # RepositoryAnalyzer
    review_summary: str = ""
    review_comments: list = []
    recommendation: str = "comment"
    # ReAct agent state
    agent_executor: object | None = None  # AgentExecutor
    mcp_tools: list = []

    class Config:
        arbitrary_types_allowed = True


def truncate_content(content: str, max_chars: int) -> str:
    """Truncate content to prevent token limit issues."""
    if len(content) <= max_chars:
        return content
    
    # Try to truncate at a logical boundary (line break)
    truncated = content[:max_chars]
    last_newline = truncated.rfind('\n')
    if last_newline > max_chars * 0.8:  # If we can truncate at 80%+ of max
        truncated = truncated[:last_newline]
    
    return truncated + f"\n\n[TRUNCATED - Content was {len(content)} chars, showing first {len(truncated)} chars]"


async def fetch_additional_data(state: ReviewState, data_type: str, mcp_analyzer) -> dict:
    """Fetch additional data on demand using MCP tools."""
    try:
        if data_type == "diff_content" and not state.diff_content:
            logger.info(
                "Fetching diff content", pr=state.review_data.pr_number
            )
            # Fetch diff from GitHub URL
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{state.review_data.diff_url}.diff"
                ) as response:
                    if response.status == 200:
                        state.diff_content = await response.text()
                    else:
                        raise Exception(f"Failed to fetch diff: {response.status}")

        elif data_type == "project_structure" and not state.project_structure:
            logger.info(
                "Analyzing project structure", pr=state.review_data.pr_number
            )
            # Clone repo and analyze structure
            analysis = await mcp_analyzer.analyze_repository(
                state.review_data.clone_url,
                state.review_data.base_branch,
                state.review_data.head_sha,
            )
            # Handle both dict and object responses
            if hasattr(analysis, 'dict'):
                state.project_structure = analysis.dict()
            elif hasattr(analysis, 'model_dump'):
                state.project_structure = analysis.model_dump()
            else:
                state.project_structure = analysis if isinstance(analysis, dict) else {}

        elif data_type == "file_contents" and not state.file_contents:
            logger.info(
                "Fetching changed file contents", pr=state.review_data.pr_number
            )
            # Get file contents for changed files from the cloned repo
            if hasattr(state, "mcp_analyzer") and state.mcp_analyzer:
                if hasattr(state.mcp_analyzer, 'get_changed_file_contents'):
                    file_contents = await state.mcp_analyzer.get_changed_file_contents(
                        state.review_data.base_sha, state.review_data.head_sha
                    )
                    state.file_contents = file_contents
                else:
                    # Method doesn't exist, skip file contents fetching
                    logger.warning("get_changed_file_contents method not available")

        return {"status": "success", "data_type": data_type}

    except Exception as e:
        logger.error(
            "Failed to fetch additional data", data_type=data_type, error=str(e)
        )
        return {"status": "error", "error": str(e)}


def parse_ai_response(response, category: str) -> list[ReviewFinding]:
    """Parse AI response into enhanced ReviewFinding objects with detailed suggestions."""
    findings = []

    try:
        # Handle different response formats
        findings_list = []
        if isinstance(response, dict):
            if "findings" in response:
                findings_list = response["findings"]
            elif "issues" in response:
                findings_list = response["issues"]
            elif "comments" in response:
                findings_list = response["comments"]
            else:
                # Response might be a single finding
                findings_list = [response] if response else []
        elif isinstance(response, list):
            findings_list = response

        # Process findings with enhancement
        for finding_data in findings_list:
            try:
                if isinstance(finding_data, dict):
                    # Enhance finding with better defaults and formatting
                    enhanced_finding = _enhance_finding_data(finding_data, category)
                    finding = ReviewFinding(**enhanced_finding)
                    findings.append(finding)
            except Exception as finding_error:
                logger.warning(
                    "Failed to parse finding",
                    finding=finding_data,
                    error=str(finding_error),
                )

    except Exception as e:
        logger.error(
            "Failed to parse AI response", category=category, error=str(e)
        )

    return findings


def _enhance_finding_data(finding_data: dict, category: str) -> dict:
    """Enhance finding data with better formatting and suggestions."""
    # Set defaults
    finding_data.setdefault("category", category)
    finding_data.setdefault("severity", "medium")
    finding_data.setdefault("message", "No message provided")
    
    # Enhance message with better formatting
    message = finding_data.get("message", "")
    if message and not message.startswith("**"):
        # Add category-specific formatting
        category_icons = {
            "logic": "🧠",
            "security": "🔒",
            "critical_bug": "🐛", 
            "naming": "📝",
            "optimization": "⚡",
            "principles": "🏗️"
        }
        
        icon = category_icons.get(category, "📌")
        category_name = category.replace("_", " ").title()
        finding_data["message"] = f"{icon} **{category_name}**: {message}"
    
    # Generate enhanced suggestions if not provided or too generic
    current_suggestion = finding_data.get("suggestion", "")
    if not current_suggestion or len(current_suggestion) < 20:
        finding_data["suggestion"] = _generate_enhanced_suggestion(
            finding_data["message"], 
            category, 
            finding_data.get("severity", "medium")
        )
    
    # Add principle violated for design issues
    if category == "principles" and not finding_data.get("principle_violated"):
        finding_data["principle_violated"] = _detect_violated_principle(finding_data["message"])
    
    return finding_data


def _generate_enhanced_suggestion(message: str, category: str, severity: str) -> str:
    """Generate detailed, actionable suggestions based on message content."""
    message_lower = message.lower()
    
    # Security-specific suggestions
    if category == "security":
        if "injection" in message_lower:
            return "🔒 Use parameterized queries, input validation, and sanitization. Consider implementing a security library for input handling."
        elif "authentication" in message_lower:
            return "🔐 Review authentication flow: ensure secure session management, implement proper token handling, and add multi-factor authentication where appropriate."
        elif "authorization" in message_lower:
            return "🛡️ Implement role-based access control (RBAC), verify permissions at every endpoint, and use principle of least privilege."
        elif "crypto" in message_lower or "encryption" in message_lower:
            return "🔐 Use industry-standard encryption libraries, ensure proper key management, and implement secure random number generation."
        else:
            return "🔒 Conduct security review: validate all inputs, implement proper error handling that doesn't leak information, and add security tests."
    
    # Logic-specific suggestions  
    elif category == "logic":
        if "condition" in message_lower or "if" in message_lower:
            return "🧠 Review conditional logic: add boundary checks, handle null/undefined cases, and consider all possible execution paths."
        elif "loop" in message_lower:
            return "🔄 Optimize loop logic: add termination conditions, handle empty collections, and consider performance implications."
        elif "exception" in message_lower or "error" in message_lower:
            return "⚠️ Implement comprehensive error handling: use specific exception types, add meaningful error messages, and ensure graceful failure."
        else:
            return "🧠 Analyze business logic: verify all requirements are met, add edge case handling, and ensure data consistency."
    
    # Performance suggestions
    elif category == "optimization":
        if "query" in message_lower or "database" in message_lower:
            return "⚡ Optimize database access: add proper indexing, use query optimization, implement connection pooling, and consider caching strategies."
        elif "algorithm" in message_lower:
            return "📊 Improve algorithm efficiency: analyze time/space complexity, consider more efficient data structures, and profile performance bottlenecks."
        elif "memory" in message_lower:
            return "💾 Optimize memory usage: implement object pooling, use lazy loading, avoid memory leaks, and consider streaming for large datasets."
        else:
            return "⚡ Performance optimization: profile critical paths, implement caching where appropriate, and consider async processing for I/O operations."
    
    # Bug-specific suggestions
    elif category == "critical_bug":
        if severity == "critical":
            return "🚨 URGENT: This issue could cause system failure. Implement immediate fixes, add comprehensive testing, and consider feature flags for rollback."
        elif "race" in message_lower:
            return "🏃 Fix race condition: implement proper synchronization, use atomic operations, and add concurrency testing."
        elif "null" in message_lower or "undefined" in message_lower:
            return "❌ Prevent null/undefined errors: add null checks, use optional chaining, implement default values, and add validation."
        else:
            return "🐛 Fix critical bug: add comprehensive testing, implement defensive programming practices, and ensure proper error recovery."
    
    # Naming suggestions
    elif category == "naming":
        return "📝 Improve naming: use domain-specific terminology, ensure names reflect functionality, maintain consistency with existing codebase, and avoid abbreviations."
    
    # Design principles suggestions
    elif category == "principles":
        if "dry" in message_lower:
            return "🏗️ Eliminate duplication: extract common functionality into reusable functions/classes, create utility modules, and establish consistent patterns."
        elif "kiss" in message_lower:
            return "✨ Simplify implementation: break down complex functions, reduce dependencies, use clear and straightforward logic, and eliminate unnecessary abstractions."
        elif "solid" in message_lower:
            return "🏛️ Apply SOLID principles: ensure single responsibility, use dependency injection, prefer composition over inheritance, and design for extensibility."
        else:
            return "🏗️ Improve design: follow established patterns, ensure loose coupling, maintain high cohesion, and make code self-documenting."
    
    # Default suggestion based on severity
    severity_suggestions = {
        "critical": "🚨 Immediate action required: This issue needs urgent attention before deployment.",
        "high": "⚠️ High priority: Address this issue before merging to maintain code quality and security.",
        "medium": "📋 Recommended improvement: Consider addressing this to enhance code maintainability.",
        "low": "💡 Minor suggestion: Nice-to-have improvement for better code quality."
    }
    
    return severity_suggestions.get(severity, "📝 Review and consider implementing the suggested improvement.")


def _detect_violated_principle(message: str) -> str:
    """Detect which design principle is violated based on message content."""
    message_lower = message.lower()
    
    if any(word in message_lower for word in ["duplicate", "repeat", "same code", "copy"]):
        return "DRY (Don't Repeat Yourself)"
    elif any(word in message_lower for word in ["complex", "complicated", "convoluted", "over"]):
        return "KISS (Keep It Simple Stupid)"
    elif "responsibility" in message_lower:
        return "Single Responsibility Principle"
    elif "depend" in message_lower:
        return "Dependency Inversion Principle"
    elif "extend" in message_lower or "modify" in message_lower:
        return "Open/Closed Principle"
    else:
        return "General Design Principles"


def generate_review_summary(findings: list[ReviewFinding]) -> tuple[str, str]:
    """Generate comprehensive review summary with detailed finding breakdown."""
    # Group findings by severity and category
    critical_findings = [f for f in findings if f.severity == "critical"]
    high_findings = [f for f in findings if f.severity == "high"]
    medium_findings = [f for f in findings if f.severity == "medium"]
    low_findings = [f for f in findings if f.severity == "low"]
    
    # Group by categories for detailed breakdown
    category_counts = {}
    category_examples = {}
    
    for finding in findings:
        category = finding.category
        category_counts[category] = category_counts.get(category, 0) + 1
        
        # Store example message for each category
        if category not in category_examples:
            category_examples[category] = finding.message[:100] + "..." if len(finding.message) > 100 else finding.message

    # Determine recommendation
    if critical_findings:
        recommendation = "request_changes"
    elif len(high_findings) >= 3:
        recommendation = "request_changes"
    elif high_findings or len(medium_findings) >= 5:
        recommendation = "comment"
    else:
        recommendation = "approve"

    # Enhanced summary generation with detailed breakdown
    total_findings = len(findings)
    if total_findings == 0:
        summary = "✅ **Review Complete**: This PR looks good! No significant logic, security, or critical issues found during comprehensive analysis."
    else:
        # Create detailed summary with findings breakdown
        summary_parts = []
        
        # Main summary line
        if critical_findings:
            summary_parts.append(f"🚨 **Critical Issues Found**: This PR requires immediate attention before merging.")
        elif len(high_findings) >= 3:
            summary_parts.append(f"⚠️ **Multiple High-Priority Issues**: This PR needs significant improvements before merging.")
        elif high_findings:
            summary_parts.append(f"📋 **Issues Identified**: Several issues found that should be addressed.")
        elif len(medium_findings) >= 5:
            summary_parts.append(f"📝 **Improvements Suggested**: Multiple opportunities for code quality enhancement.")
        else:
            summary_parts.append(f"🔍 **Minor Issues Found**: Some improvements recommended for better code quality.")
        
        # Detailed breakdown by severity
        severity_breakdown = []
        if critical_findings:
            severity_breakdown.append(f"🔴 **{len(critical_findings)} Critical** - Immediate action required")
        if high_findings:
            severity_breakdown.append(f"🟠 **{len(high_findings)} High** - Should be addressed before merge")
        if medium_findings:
            severity_breakdown.append(f"🟡 **{len(medium_findings)} Medium** - Recommended improvements")
        if low_findings:
            severity_breakdown.append(f"🔵 **{len(low_findings)} Low** - Minor suggestions")
            
        if severity_breakdown:
            summary_parts.append("\n**Severity Breakdown:**\n" + " | ".join(severity_breakdown))
        
        # Category breakdown with examples
        if category_counts:
            category_breakdown = []
            category_icons = {
                "logic": "🧠",
                "security": "🔒", 
                "critical_bug": "🐛",
                "naming": "📝",
                "optimization": "⚡",
                "principles": "🏗️"
            }
            
            for category, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
                icon = category_icons.get(category, "📌")
                category_name = category.replace("_", " ").title()
                example = category_examples.get(category, "")
                category_breakdown.append(f"{icon} **{category_name}** ({count}): {example}")
            
            if category_breakdown:
                summary_parts.append("\n**Key Areas:**")
                summary_parts.extend([f"• {item}" for item in category_breakdown[:3]])  # Show top 3
                
                if len(category_breakdown) > 3:
                    summary_parts.append(f"• ... and {len(category_breakdown) - 3} more areas")
        
        # Action items based on findings
        if critical_findings or high_findings:
            summary_parts.append(f"\n**Next Steps:**")
            if critical_findings:
                summary_parts.append(f"• 🚨 Address {len(critical_findings)} critical security/logic issue(s)")
            if high_findings:
                summary_parts.append(f"• ⚠️ Fix {len(high_findings)} high-priority issue(s)")
            if medium_findings:
                summary_parts.append(f"• 📝 Consider {len(medium_findings)} improvement suggestion(s)")

        summary = "\n".join(summary_parts)

    return summary, recommendation


def get_severity_counts(findings: list[ReviewFinding]) -> dict:
    """Get counts of findings by severity level."""
    def get_severity(finding):
        if hasattr(finding, 'severity'):
            return finding.severity
        elif isinstance(finding, dict):
            return finding.get('severity', 'medium')
        else:
            return 'medium'

    total_findings = len(findings)
    critical_count = len([f for f in findings if get_severity(f) == "critical"])
    high_count = len([f for f in findings if get_severity(f) == "high"])
    medium_count = len([f for f in findings if get_severity(f) == "medium"])
    low_count = len([f for f in findings if get_severity(f) == "low"])
    
    return {
        "total_findings": total_findings,
        "critical_count": critical_count,
        "high_count": high_count,
        "medium_count": medium_count,
        "low_count": low_count,
    }