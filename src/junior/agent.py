"""Core AI agent for code review."""

import asyncio
from typing import Dict, List, Optional, Tuple

import structlog
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from .config import settings
from .models import CodeReviewRequest, CodeReviewResult, FileChange, ReviewComment

logger = structlog.get_logger(__name__)


class ReviewState(BaseModel):
    """State for the code review graph."""

    request: CodeReviewRequest
    file_changes: List[FileChange] = []
    comments: List[ReviewComment] = []
    summary: Optional[str] = None
    security_issues: List[ReviewComment] = []
    performance_issues: List[ReviewComment] = []
    style_issues: List[ReviewComment] = []
    complexity_issues: List[ReviewComment] = []
    error: Optional[str] = None


class CodeReviewAgent:
    """AI agent for reviewing code changes."""

    def __init__(self):
        """Initialize the code review agent."""
        self.logger = logger.bind(component="CodeReviewAgent")
        self._setup_llm()
        self._setup_graph()

    def _setup_llm(self) -> None:
        """Set up the language model."""
        if settings.anthropic_api_key:
            self.llm = ChatAnthropic(
                model="claude-3-5-sonnet-20241022",
                api_key=settings.anthropic_api_key,
                temperature=settings.temperature,
                max_tokens=settings.max_tokens,
            )
        elif settings.openai_api_key:
            self.llm = ChatOpenAI(
                model=settings.default_model,
                api_key=settings.openai_api_key,
                temperature=settings.temperature,
                max_tokens=settings.max_tokens,
            )
        else:
            raise ValueError("No AI API key provided")

        self.parser = StrOutputParser()

    def _setup_graph(self) -> None:
        """Set up the LangGraph workflow."""
        workflow = StateGraph(ReviewState)

        # Add nodes
        workflow.add_node("analyze_files", self._analyze_files)
        workflow.add_node("security_review", self._security_review)
        workflow.add_node("performance_review", self._performance_review)
        workflow.add_node("style_review", self._style_review)
        workflow.add_node("complexity_review", self._complexity_review)
        workflow.add_node("generate_summary", self._generate_summary)

        # Set entry point
        workflow.set_entry_point("analyze_files")

        # Add edges
        workflow.add_edge("analyze_files", "security_review")
        workflow.add_edge("security_review", "performance_review")
        workflow.add_edge("performance_review", "style_review")
        workflow.add_edge("style_review", "complexity_review")
        workflow.add_edge("complexity_review", "generate_summary")
        workflow.add_edge("generate_summary", END)

        self.graph = workflow.compile()

    async def _analyze_files(self, state: ReviewState) -> ReviewState:
        """Analyze the changed files."""
        self.logger.info("Analyzing files", file_count=len(state.request.files))
        
        # This would typically parse diff and extract file changes
        # For now, we'll use the provided file changes
        state.file_changes = state.request.files
        
        return state

    async def _security_review(self, state: ReviewState) -> ReviewState:
        """Perform security review."""
        if not settings.enable_security_checks:
            return state

        self.logger.info("Performing security review")
        
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content="""You are a security expert reviewing code changes.
            Look for:
            - SQL injection vulnerabilities
            - XSS vulnerabilities  
            - Authentication/authorization issues
            - Insecure data handling
            - Hard-coded secrets or credentials
            - Insecure cryptographic practices
            - Input validation issues
            
            For each issue found, provide:
            - Line number (if applicable)
            - Severity (low/medium/high/critical)
            - Description of the issue
            - Suggested fix
            
            Return only specific security issues found, not general advice."""),
            HumanMessage(content=f"Review these code changes for security issues:\n\n{self._format_changes(state.file_changes)}")
        ])

        try:
            chain = prompt | self.llm | self.parser
            response = await chain.ainvoke({})
            
            # Parse response and create ReviewComment objects
            security_comments = self._parse_review_response(response, "security")
            state.security_issues = security_comments
            state.comments.extend(security_comments)
            
        except Exception as e:
            self.logger.error("Security review failed", error=str(e))
            state.error = f"Security review failed: {e}"

        return state

    async def _performance_review(self, state: ReviewState) -> ReviewState:
        """Perform performance review."""
        if not settings.enable_performance_checks:
            return state

        self.logger.info("Performing performance review")
        
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content="""You are a performance expert reviewing code changes.
            Look for:
            - Inefficient algorithms or data structures
            - Memory leaks or excessive memory usage
            - Unnecessary database queries (N+1 problems)
            - Blocking operations that should be async
            - Large file operations without streaming
            - Inefficient loops or iterations
            - Missing caching opportunities
            
            Focus on actual performance bottlenecks, not micro-optimizations."""),
            HumanMessage(content=f"Review these code changes for performance issues:\n\n{self._format_changes(state.file_changes)}")
        ])

        try:
            chain = prompt | self.llm | self.parser
            response = await chain.ainvoke({})
            
            performance_comments = self._parse_review_response(response, "performance")
            state.performance_issues = performance_comments
            state.comments.extend(performance_comments)
            
        except Exception as e:
            self.logger.error("Performance review failed", error=str(e))

        return state

    async def _style_review(self, state: ReviewState) -> ReviewState:
        """Perform style review."""
        if not settings.enable_style_checks:
            return state

        self.logger.info("Performing style review")
        
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content="""You are a code style expert reviewing code changes.
            Look for:
            - Inconsistent naming conventions
            - Poor function/variable names
            - Missing or inadequate documentation
            - Code that violates language-specific style guides
            - Inconsistent formatting (if not handled by auto-formatters)
            - Missing type hints (for Python)
            
            Focus on readability and maintainability issues."""),
            HumanMessage(content=f"Review these code changes for style issues:\n\n{self._format_changes(state.file_changes)}")
        ])

        try:
            chain = prompt | self.llm | self.parser
            response = await chain.ainvoke({})
            
            style_comments = self._parse_review_response(response, "style")
            state.style_issues = style_comments
            state.comments.extend(style_comments)
            
        except Exception as e:
            self.logger.error("Style review failed", error=str(e))

        return state

    async def _complexity_review(self, state: ReviewState) -> ReviewState:
        """Perform complexity review."""
        if not settings.enable_complexity_checks:
            return state

        self.logger.info("Performing complexity review")
        
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content="""You are a code complexity expert reviewing code changes.
            Look for:
            - Functions that are too long or complex
            - Deeply nested conditions or loops
            - High cyclomatic complexity
            - Code duplication
            - Classes with too many responsibilities
            - Complex inheritance hierarchies
            
            Suggest refactoring opportunities to improve maintainability."""),
            HumanMessage(content=f"Review these code changes for complexity issues:\n\n{self._format_changes(state.file_changes)}")
        ])

        try:
            chain = prompt | self.llm | self.parser
            response = await chain.ainvoke({})
            
            complexity_comments = self._parse_review_response(response, "complexity")
            state.complexity_issues = complexity_comments
            state.comments.extend(complexity_comments)
            
        except Exception as e:
            self.logger.error("Complexity review failed", error=str(e))

        return state

    async def _generate_summary(self, state: ReviewState) -> ReviewState:
        """Generate review summary."""
        self.logger.info("Generating review summary")
        
        total_issues = len(state.comments)
        security_count = len(state.security_issues)
        performance_count = len(state.performance_issues)
        style_count = len(state.style_issues)
        complexity_count = len(state.complexity_issues)
        
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content="""Generate a concise summary of the code review.
            Include:
            - Overall assessment (approve/request changes/comment)
            - Key issues found by category
            - Positive aspects of the code
            - Priority recommendations
            
            Keep it professional and constructive."""),
            HumanMessage(content=f"""Code review results:
            - Total issues: {total_issues}
            - Security issues: {security_count}
            - Performance issues: {performance_count}
            - Style issues: {style_count}
            - Complexity issues: {complexity_count}
            
            Issues found:
            {self._format_all_comments(state.comments)}""")
        ])

        try:
            chain = prompt | self.llm | self.parser
            state.summary = await chain.ainvoke({})
        except Exception as e:
            self.logger.error("Summary generation failed", error=str(e))
            state.summary = f"Failed to generate summary: {e}"

        return state

    def _format_changes(self, file_changes: List[FileChange]) -> str:
        """Format file changes for AI review."""
        formatted = []
        for change in file_changes:
            formatted.append(f"File: {change.filename}")
            formatted.append(f"Status: {change.status}")
            if change.diff:
                formatted.append(f"Changes:\n{change.diff}")
            formatted.append("---")
        return "\n".join(formatted)

    def _format_all_comments(self, comments: List[ReviewComment]) -> str:
        """Format all comments for summary generation."""
        if not comments:
            return "No issues found."
        
        formatted = []
        for comment in comments:
            formatted.append(f"- {comment.category.upper()}: {comment.message}")
            if comment.line_number:
                formatted.append(f"  Line {comment.line_number}")
            if comment.suggestion:
                formatted.append(f"  Suggestion: {comment.suggestion}")
        return "\n".join(formatted)

    def _parse_review_response(self, response: str, category: str) -> List[ReviewComment]:
        """Parse AI response into ReviewComment objects."""
        # This is a simplified parser - in reality you'd want more robust parsing
        comments = []
        if response and response.strip():
            # Simple parsing - split by lines and create basic comments
            lines = response.strip().split('\n')
            for line in lines:
                if line.strip() and not line.startswith('#'):
                    comments.append(ReviewComment(
                        category=category,
                        message=line.strip(),
                        severity="medium"  # Default severity
                    ))
        return comments

    async def review_code(self, request: CodeReviewRequest) -> CodeReviewResult:
        """Perform a complete code review."""
        self.logger.info("Starting code review", pr_number=request.pr_number)
        
        try:
            # Initialize state
            state = ReviewState(request=request)
            
            # Run the review workflow
            final_state = await self.graph.ainvoke(state)
            
            # Create result
            result = CodeReviewResult(
                pr_number=request.pr_number,
                repository=request.repository,
                comments=final_state.comments,
                summary=final_state.summary or "Review completed",
                security_issues_count=len(final_state.security_issues),
                performance_issues_count=len(final_state.performance_issues),
                style_issues_count=len(final_state.style_issues),
                complexity_issues_count=len(final_state.complexity_issues),
            )
            
            self.logger.info("Code review completed", 
                           total_comments=len(result.comments),
                           security_issues=result.security_issues_count,
                           performance_issues=result.performance_issues_count)
            
            return result
            
        except Exception as e:
            self.logger.error("Code review failed", error=str(e))
            return CodeReviewResult(
                pr_number=request.pr_number,
                repository=request.repository,
                comments=[],
                summary=f"Review failed: {e}",
                security_issues_count=0,
                performance_issues_count=0,
                style_issues_count=0,
                complexity_issues_count=0,
            )