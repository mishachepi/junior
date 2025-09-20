"""Specialized review agent for logical and critical analysis."""

import structlog
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from ..config import settings
from ..models import ReviewData, ReviewCategory, ReviewComment, Severity
from .tools import RepositoryAnalyzer

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


class LogicalReviewState(BaseModel):
    """State for logical review workflow."""

    review_data: ReviewData
    diff_content: str = ""
    file_contents: dict[str, str] = {}
    project_structure: dict = {}
    findings: list[ReviewFinding] = []
    current_step: str = "start"
    error: str | None = None
    mcp_analyzer: RepositoryAnalyzer | None = None

    class Config:
        arbitrary_types_allowed = True


class LogicalReviewAgent:
    """Specialized agent for logical and critical code review."""

    def __init__(self):
        self.logger = logger.bind(component="LogicalReviewAgent")
        self._setup_llm()
        self._setup_review_graph()
        self.mcp_analyzer = RepositoryAnalyzer()

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

    def _setup_review_graph(self) -> None:
        """Set up specialized review workflow."""
        workflow = StateGraph(LogicalReviewState)

        # Add review steps
        workflow.add_node("analyze_logic", self._analyze_project_logic)
        workflow.add_node("check_security", self._check_logical_security)
        workflow.add_node("find_critical_bugs", self._find_critical_bugs)
        workflow.add_node("review_naming", self._review_naming_conventions)
        workflow.add_node("check_optimization", self._check_code_optimization)
        workflow.add_node("verify_principles", self._verify_design_principles)
        workflow.add_node("generate_summary", self._generate_review_summary)

        # Set entry point
        workflow.set_entry_point("analyze_logic")

        # Define workflow
        workflow.add_edge("analyze_logic", "check_security")
        workflow.add_edge("check_security", "find_critical_bugs")
        workflow.add_edge("find_critical_bugs", "review_naming")
        workflow.add_edge("review_naming", "check_optimization")
        workflow.add_edge("check_optimization", "verify_principles")
        workflow.add_edge("verify_principles", "generate_summary")
        workflow.add_edge("generate_summary", END)

        self.review_graph = workflow.compile()

    async def _fetch_additional_data(
        self, state: LogicalReviewState, data_type: str
    ) -> dict:
        """Fetch additional data on demand using MCP tools."""
        try:
            if data_type == "diff_content" and not state.diff_content:
                self.logger.info(
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
                self.logger.info(
                    "Analyzing project structure", pr=state.review_data.pr_number
                )
                # Clone repo and analyze structure
                analysis = await self.mcp_analyzer.analyze_repository(
                    state.review_data.clone_url,
                    state.review_data.base_branch,
                    state.review_data.head_sha,
                )
                state.project_structure = analysis.dict()

            elif data_type == "file_contents" and not state.file_contents:
                self.logger.info(
                    "Fetching changed file contents", pr=state.review_data.pr_number
                )
                # Get file contents for changed files from the cloned repo
                if hasattr(state, "mcp_analyzer") and state.mcp_analyzer:
                    file_contents = await state.mcp_analyzer.get_changed_file_contents(
                        state.review_data.base_sha, state.review_data.head_sha
                    )
                    state.file_contents = file_contents

            return {"status": "success", "data_type": data_type}

        except Exception as e:
            self.logger.error(
                "Failed to fetch additional data", data_type=data_type, error=str(e)
            )
            return {"status": "error", "error": str(e)}

    def _parse_ai_response(self, response, category: str) -> list[ReviewFinding]:
        """Parse AI response into ReviewFinding objects."""
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

            # Process findings
            for finding_data in findings_list:
                try:
                    if isinstance(finding_data, dict):
                        # Ensure required fields exist
                        finding_data.setdefault("category", category)
                        finding_data.setdefault("severity", "medium")
                        finding_data.setdefault("message", "No message provided")

                        finding = ReviewFinding(**finding_data)
                        findings.append(finding)
                except Exception as finding_error:
                    self.logger.warning(
                        "Failed to parse finding",
                        finding=finding_data,
                        error=str(finding_error),
                    )

        except Exception as e:
            self.logger.error(
                "Failed to parse AI response", category=category, error=str(e)
            )

        return findings

    async def _analyze_project_logic(
        self, state: LogicalReviewState
    ) -> LogicalReviewState:
        """Analyze overall project logic and architecture."""
        self.logger.info("Analyzing project logic", pr=state.review_data.pr_number)

        # Fetch data on demand
        if not state.diff_content:
            await self._fetch_additional_data(state, "diff_content")
        if not state.project_structure:
            await self._fetch_additional_data(state, "project_structure")

        prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessage(
                    content="""You are a senior software architect reviewing code changes.
            Analyze the diff for:
            
            1. **Logic Flow Issues**:
               - Incorrect conditional logic
               - Missing edge cases
               - Unreachable code paths
               - Logic that contradicts business requirements
            
            2. **Architecture Violations**:
               - Breaking established patterns
               - Tight coupling introduction
               - Separation of concerns violations
               - Inappropriate abstraction levels
            
            3. **Data Flow Problems**:
               - Incorrect state management
               - Race conditions potential
               - Data consistency issues
               - Missing validation steps
            
            Return findings as JSON in this exact format:
            {
              "findings": [
                {
                  "category": "logic",
                  "severity": "critical|high|medium|low",
                  "message": "Clear description of the issue",
                  "file_path": "path/to/file.py",
                  "line_number": 42,
                  "suggestion": "How to fix this issue",
                  "principle_violated": "Which principle/rule is violated"
                }
              ]
            }
            Only report actual logic issues, not style or linting problems."""
                ),
                HumanMessage(
                    content=f"""Project: {state.review_data.repository}
            PR: #{state.review_data.pr_number}
            Title: {state.review_data.title}
            Author: {state.review_data.author}
            
            Diff content:
            {state.diff_content}
            
            Project structure context:
            {state.project_structure}
            
            Analyze the logic and architecture implications of these changes."""
                ),
            ]
        )

        try:
            chain = prompt | self.llm | JsonOutputParser()
            response = await chain.ainvoke({})

            findings = self._parse_ai_response(response, "logic")
            state.findings.extend(findings)

            self.logger.info(
                "Logic analysis completed",
                findings_count=len(findings),
                pr=state.review_data.pr_number,
            )

        except Exception as e:
            self.logger.error("Logic analysis failed", error=str(e))
            state.error = f"Logic analysis failed: {e}"

        state.current_step = "logic_complete"
        return state

    async def _check_logical_security(
        self, state: LogicalReviewState
    ) -> LogicalReviewState:
        """Check for logical security vulnerabilities."""
        self.logger.info("Checking logical security", pr=state.review_data.pr_number)

        # Ensure diff content is available
        if not state.diff_content:
            await self._fetch_additional_data(state, "diff_content")

        prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessage(
                    content="""You are a security expert focusing on logical vulnerabilities.
            Look for these critical security issues:
            
            1. **Authentication/Authorization Logic**:
               - Missing permission checks
               - Privilege escalation paths
               - Authentication bypass conditions
               - Role-based access control violations
            
            2. **Business Logic Vulnerabilities**:
               - Race conditions in critical operations
               - Integer overflow/underflow in calculations
               - Logic flaws in financial/sensitive operations
               - State manipulation vulnerabilities
            
            3. **Data Security Logic**:
               - Unvalidated redirects
               - Path traversal vulnerabilities
               - Logic flaws in encryption/decryption
               - Insecure state transitions
            
            4. **Zero-Day Potential**:
               - Novel attack vectors in application logic
               - Undocumented behavior combinations
               - Logic that could be chained for exploitation
            
            Focus on LOGICAL security flaws, not implementation details like SQL injection.
            Return findings as JSON in this exact format:
            {
              "findings": [
                {
                  "category": "security",
                  "severity": "critical|high|medium|low",
                  "message": "Clear description of the security vulnerability",
                  "file_path": "path/to/file.py",
                  "line_number": 42,
                  "suggestion": "How to fix this vulnerability",
                  "principle_violated": "Security principle violated"
                }
              ]
            }"""
                ),
                HumanMessage(
                    content=f"""Analyze this diff for logical security vulnerabilities:
            
            {state.diff_content}
            
            Consider the broader application context and potential attack scenarios."""
                ),
            ]
        )

        try:
            chain = prompt | self.llm | JsonOutputParser()
            response = await chain.ainvoke({})

            findings = self._parse_ai_response(response, "security")
            state.findings.extend(findings)

            self.logger.info(
                "Security analysis completed",
                findings_count=len(findings),
                pr=state.review_data.pr_number,
            )

        except Exception as e:
            self.logger.error("Security analysis failed", error=str(e))

        state.current_step = "security_complete"
        return state

    async def _find_critical_bugs(
        self, state: LogicalReviewState
    ) -> LogicalReviewState:
        """Find critical bugs and potential zero-days."""
        self.logger.info("Finding critical bugs", pr=state.review_data.pr_number)

        prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessage(
                    content="""You are a bug hunter specializing in critical vulnerabilities.
            Search for:
            
            1. **Memory Safety Issues** (for applicable languages):
               - Buffer overflows
               - Use-after-free conditions
               - Double-free vulnerabilities
               - Null pointer dereferences
            
            2. **Critical Logic Bugs**:
               - Off-by-one errors in critical paths
               - Incorrect boundary checks
               - Resource leak conditions
               - Deadlock potential
            
            3. **Zero-Day Potential**:
               - Unusual code patterns that could be exploited
               - Complex interactions between components
               - Edge cases in security-critical functions
               - Novel vulnerability patterns
            
            4. **Data Corruption Risks**:
               - Concurrent access without proper locking
               - Incorrect data structure manipulation
               - Missing transaction boundaries
               - State corruption possibilities
            
            Prioritize findings that could lead to:
            - Remote code execution
            - Privilege escalation  
            - Data exfiltration
            - Service disruption
            
            Return JSON with critical findings only."""
                ),
                HumanMessage(
                    content=f"""Hunt for critical bugs in this code change:
            
            {state.diff_content}
            
            Focus on exploitable vulnerabilities and critical system failures."""
                ),
            ]
        )

        try:
            chain = prompt | self.llm | JsonOutputParser()
            response = await chain.ainvoke({})

            findings = self._parse_ai_response(response, "critical_bug")
            state.findings.extend(findings)

            self.logger.info(
                "Critical bug analysis completed",
                findings_count=len(findings),
                pr=state.review_data.pr_number,
            )

        except Exception as e:
            self.logger.error("Bug hunting failed", error=str(e))

        state.current_step = "bugs_complete"
        return state

    async def _review_naming_conventions(
        self, state: LogicalReviewState
    ) -> LogicalReviewState:
        """Review naming conventions that impact readability."""
        self.logger.info("Reviewing naming conventions", pr=state.review_data.pr_number)

        prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessage(
                    content="""Review naming conventions for readability and maintainability.
            Focus on issues that linters cannot catch:
            
            1. **Semantic Clarity**:
               - Variables/functions that don't match their actual purpose
               - Misleading names that suggest different behavior
               - Ambiguous abbreviations
               - Names that violate domain conventions
            
            2. **Cognitive Load**:
               - Overly complex or cryptic names
               - Inconsistent naming patterns within the same module
               - Names that require extensive context to understand
               - Similar names for different concepts
            
            3. **Business Logic Clarity**:
               - Technical names for business concepts
               - Generic names for specific domain entities
               - Names that don't reflect business rules
            
            4. **API Design**:
               - Public interface names that don't follow conventions
               - Method names that don't indicate side effects
               - Parameter names that don't clarify usage
            
            Ignore style issues like camelCase vs snake_case.
            Return JSON with naming improvement suggestions."""
                ),
                HumanMessage(
                    content=f"""Review naming in this code change:
            
            {state.diff_content}
            
            Focus on clarity, domain appropriateness, and maintainability."""
                ),
            ]
        )

        try:
            chain = prompt | self.llm | JsonOutputParser()
            response = await chain.ainvoke({})

            findings = self._parse_ai_response(response, "naming")
            state.findings.extend(findings)

            self.logger.info(
                "Naming review completed",
                findings_count=len(findings),
                pr=state.review_data.pr_number,
            )

        except Exception as e:
            self.logger.error("Naming review failed", error=str(e))

        state.current_step = "naming_complete"
        return state

    async def _check_code_optimization(
        self, state: LogicalReviewState
    ) -> LogicalReviewState:
        """Check for code optimization opportunities."""
        self.logger.info(
            "Checking optimization opportunities", pr=state.review_data.pr_number
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessage(
                    content="""Analyze code for significant optimization opportunities:
            
            1. **Algorithmic Improvements**:
               - Inefficient algorithms (O(n²) when O(n log n) possible)
               - Redundant computations
               - Unnecessary nested loops
               - Missing memoization/caching opportunities
            
            2. **Resource Usage**:
               - Memory leaks or excessive allocations
               - Unclosed resources
               - Inefficient data structures for the use case
               - Blocking operations that could be async
            
            3. **Database/Network Optimization**:
               - N+1 query problems
               - Missing database indexes implications
               - Unnecessary API calls
               - Large data transfers that could be paginated
            
            4. **Performance Anti-patterns**:
               - String concatenation in loops
               - Repeated expensive operations
               - Synchronous I/O in performance-critical paths
               - Missing batch operations
            
            Focus on impactful optimizations, not micro-optimizations.
            Return JSON with optimization suggestions."""
                ),
                HumanMessage(
                    content=f"""Analyze optimization opportunities in:
            
            {state.diff_content}
            
            Consider the application context and user impact."""
                ),
            ]
        )

        try:
            chain = prompt | self.llm | JsonOutputParser()
            response = await chain.ainvoke({})

            findings = self._parse_ai_response(response, "optimization")
            state.findings.extend(findings)

            self.logger.info(
                "Optimization analysis completed",
                findings_count=len(findings),
                pr=state.review_data.pr_number,
            )

        except Exception as e:
            self.logger.error("Optimization analysis failed", error=str(e))

        state.current_step = "optimization_complete"
        return state

    async def _verify_design_principles(
        self, state: LogicalReviewState
    ) -> LogicalReviewState:
        """Verify adherence to DRY and KISS principles."""
        self.logger.info("Verifying design principles", pr=state.review_data.pr_number)

        prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessage(
                    content="""Evaluate adherence to core design principles:
            
            1. **DRY (Don't Repeat Yourself)**:
               - Duplicated logic that should be extracted
               - Similar functions that could be generalized
               - Repeated validation or transformation logic
               - Copy-pasted code blocks with minor variations
            
            2. **KISS (Keep It Simple, Stupid)**:
               - Overly complex solutions to simple problems
               - Unnecessary abstraction layers
               - Complex conditionals that could be simplified
               - Over-engineered solutions
            
            3. **Single Responsibility**:
               - Functions/classes doing too many things
               - Mixed concerns in single methods
               - God objects or utility dumping grounds
            
            4. **Open/Closed Principle**:
               - Modifications that break existing functionality
               - Hard-coded values that should be configurable
               - Extensions that require core changes
            
            5. **Maintainability Issues**:
               - Code that's hard to test
               - Tight coupling between components
               - Hidden dependencies
               - Magic numbers or unclear constants
            
            Return JSON with principle violations and refactoring suggestions."""
                ),
                HumanMessage(
                    content=f"""Evaluate design principle adherence in:
            
            {state.diff_content}
            
            Suggest concrete refactoring improvements."""
                ),
            ]
        )

        try:
            chain = prompt | self.llm | JsonOutputParser()
            response = await chain.ainvoke({})

            findings = self._parse_ai_response(response, "principles")
            state.findings.extend(findings)

            self.logger.info(
                "Design principles analysis completed",
                findings_count=len(findings),
                pr=state.review_data.pr_number,
            )

        except Exception as e:
            self.logger.error("Design principles analysis failed", error=str(e))

        state.current_step = "principles_complete"
        return state

    async def _generate_review_summary(
        self, state: LogicalReviewState
    ) -> LogicalReviewState:
        """Generate comprehensive review summary."""
        self.logger.info("Generating review summary", pr=state.review_data.pr_number)

        # Group findings by severity
        critical_findings = [f for f in state.findings if f.severity == "critical"]
        high_findings = [f for f in state.findings if f.severity == "high"]
        medium_findings = [f for f in state.findings if f.severity == "medium"]
        low_findings = [f for f in state.findings if f.severity == "low"]

        # Determine recommendation
        if critical_findings:
            recommendation = "request_changes"
        elif len(high_findings) >= 3:
            recommendation = "request_changes"
        elif high_findings or len(medium_findings) >= 5:
            recommendation = "comment"
        else:
            recommendation = "approve"

        prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessage(
                    content="""Generate a comprehensive code review summary.
            
            Structure your response as:
            1. Executive Summary (2-3 sentences)
            2. Critical Issues (if any)
            3. Key Recommendations
            4. Positive Aspects
            5. Next Steps
            
            Be constructive and specific. Focus on the most impactful issues first.
            Provide actionable guidance for addressing findings."""
                ),
                HumanMessage(
                    content=f"""Create review summary for PR #{state.review_data.pr_number}:
            
            Critical findings ({len(critical_findings)}):
            {[f.message for f in critical_findings]}
            
            High severity findings ({len(high_findings)}):
            {[f.message for f in high_findings]}
            
            Medium severity findings ({len(medium_findings)}):
            {[f.message for f in medium_findings]}
            
            Low severity findings ({len(low_findings)}):
            {[f.message for f in low_findings]}
            
            Recommendation: {recommendation}"""
                ),
            ]
        )

        try:
            chain = prompt | self.llm
            summary = await chain.ainvoke({})

            # Store final results
            state.current_step = "complete"

            # Convert findings to review comments
            review_comments = []
            for finding in state.findings:
                severity_map = {
                    "critical": Severity.CRITICAL,
                    "high": Severity.HIGH,
                    "medium": Severity.MEDIUM,
                    "low": Severity.LOW,
                }

                category_map = {
                    "logic": ReviewCategory.LOGIC,
                    "security": ReviewCategory.SECURITY,
                    "performance": ReviewCategory.PERFORMANCE,
                    "style": ReviewCategory.STYLE,
                    "complexity": ReviewCategory.COMPLEXITY,
                    "naming": ReviewCategory.STYLE,
                    "optimization": ReviewCategory.PERFORMANCE,
                    "principles": ReviewCategory.LOGIC,
                }

                comment = ReviewComment(
                    category=category_map.get(
                        finding.category.lower(), ReviewCategory.LOGIC
                    ),
                    message=finding.message,
                    filename=finding.file_path,
                    line_number=finding.line_number,
                    severity=severity_map.get(
                        finding.severity.lower(), Severity.MEDIUM
                    ),
                    suggestion=finding.suggestion,
                    rule=finding.principle_violated,
                )
                review_comments.append(comment)

            # Store for return
            state.review_summary = summary
            state.review_comments = review_comments
            state.recommendation = recommendation

        except Exception as e:
            self.logger.error("Summary generation failed", error=str(e))
            state.error = f"Summary generation failed: {e}"

        return state

    async def review_pull_request(
        self,
        review_data: ReviewData,
        diff_content: str = "",
        file_contents: dict[str, str] = None,
        project_structure: dict = None,
    ) -> dict:
        """Perform comprehensive logical review of a pull request."""
        self.logger.info(
            "Starting logical review",
            repo=review_data.repository,
            pr=review_data.pr_number,
        )

        try:
            # Initialize state with minimal data - additional data fetched on demand
            state = LogicalReviewState(
                review_data=review_data,
                diff_content=diff_content,
                file_contents=file_contents or {},
                project_structure=project_structure or {},
                mcp_analyzer=self.mcp_analyzer,
            )

            # Run review workflow
            final_state = await self.review_graph.ainvoke(state)

            # Return structured results
            return {
                "repository": final_state.review_data.repository,
                "pr_number": final_state.review_data.pr_number,
                "findings": [finding.dict() for finding in final_state.findings],
                "summary": getattr(final_state, "review_summary", "Review completed"),
                "recommendation": getattr(final_state, "recommendation", "comment"),
                "comments": [
                    comment.dict()
                    for comment in getattr(final_state, "review_comments", [])
                ],
                "critical_count": len(
                    [f for f in final_state.findings if f.severity == "critical"]
                ),
                "high_count": len(
                    [f for f in final_state.findings if f.severity == "high"]
                ),
                "medium_count": len(
                    [f for f in final_state.findings if f.severity == "medium"]
                ),
                "low_count": len(
                    [f for f in final_state.findings if f.severity == "low"]
                ),
                "total_findings": len(final_state.findings),
                "error": final_state.error,
            }

        except Exception as e:
            self.logger.error("Logical review failed", error=str(e))
            return {
                "repository": review_data.repository,
                "pr_number": review_data.pr_number,
                "findings": [],
                "summary": f"Review failed: {e}",
                "recommendation": "comment",
                "comments": [],
                "error": str(e),
            }
