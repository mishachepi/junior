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
from ..models import ReviewCategory, ReviewComment, ReviewData, Severity
from . import prompts
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


class ReviewState(BaseModel):
    """State for review workflow."""

    review_data: ReviewData
    diff_content: str = ""
    file_contents: dict[str, str] = {}
    project_structure: dict = {}
    findings: list[ReviewFinding] = []
    current_step: str = "start"
    error: str | None = None
    mcp_analyzer: RepositoryAnalyzer | None = None
    review_summary: str = ""
    review_comments: list = []
    recommendation: str = "comment"

    class Config:
        arbitrary_types_allowed = True


class ReviewAgent:
    """Specialized agent for logical and critical code review."""

    def __init__(self):
        self.logger = logger.bind(component="ReviewAgent")
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
        workflow = StateGraph(ReviewState)

        # Add review steps
        workflow.add_node("analyze_logic", self._analyze_project_logic)
        workflow.add_node("check_security", self._check_logical_security)
        # workflow.add_node("find_critical_bugs", self._find_critical_bugs)
        # workflow.add_node("review_naming", self._review_naming_conventions)
        # workflow.add_node("check_optimization", self._check_code_optimization)
        # workflow.add_node("verify_principles", self._verify_design_principles)
        workflow.add_node("generate_summary", self._generate_review_summary)

        # Set entry point
        workflow.set_entry_point("analyze_logic")

        # Define workflow
        workflow.add_edge("analyze_logic", "check_security")
        workflow.add_edge("check_security", "generate_summary")
        # workflow.add_edge("check_security", "find_critical_bugs")
        # workflow.add_edge("find_critical_bugs", "review_naming")
        # workflow.add_edge("review_naming", "check_optimization")
        # workflow.add_edge("check_optimization", "verify_principles")
        # workflow.add_edge("verify_principles", "generate_summary")
        workflow.add_edge("generate_summary", END)

        self.review_graph = workflow.compile()

    def _truncate_content(self, content: str, max_chars: int) -> str:
        """Truncate content to prevent token limit issues."""
        if len(content) <= max_chars:
            return content
        
        # Try to truncate at a logical boundary (line break)
        truncated = content[:max_chars]
        last_newline = truncated.rfind('\n')
        if last_newline > max_chars * 0.8:  # If we can truncate at 80%+ of max
            truncated = truncated[:last_newline]
        
        return truncated + f"\n\n[TRUNCATED - Content was {len(content)} chars, showing first {len(truncated)} chars]"

    async def _fetch_additional_data(
        self, state: ReviewState, data_type: str
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
                # Handle both dict and object responses
                if hasattr(analysis, 'dict'):
                    state.project_structure = analysis.dict()
                elif hasattr(analysis, 'model_dump'):
                    state.project_structure = analysis.model_dump()
                else:
                    state.project_structure = analysis if isinstance(analysis, dict) else {}

            elif data_type == "file_contents" and not state.file_contents:
                self.logger.info(
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
                        self.logger.warning("get_changed_file_contents method not available")

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
        self, state: ReviewState
    ) -> ReviewState:
        """Analyze overall project logic and architecture."""
        self.logger.info("Analyzing project logic", pr=state.review_data.pr_number)

        # Fetch data on demand
        if not state.diff_content:
            await self._fetch_additional_data(state, "diff_content")
        if not state.project_structure:
            await self._fetch_additional_data(state, "project_structure")

        # Truncate content to prevent token limits
        truncated_diff = self._truncate_content(state.diff_content, settings.max_diff_chars)
        truncated_structure = self._truncate_content(str(state.project_structure), settings.max_structure_chars)
        
        prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessage(content=prompts.ANALYZE_PROJECT_LOGIC_PROMPT),
                HumanMessage(
                    content=f"""Project: {state.review_data.repository}
            PR: #{state.review_data.pr_number}
            Title: {state.review_data.title}
            Author: {state.review_data.author}
            
            Diff content:
            {truncated_diff}
            
            Project structure context:
            {truncated_structure}
            
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
        self, state: ReviewState
    ) -> ReviewState:
        """Check for logical security vulnerabilities."""
        self.logger.info("Checking logical security", pr=state.review_data.pr_number)

        # Ensure diff content is available
        if not state.diff_content:
            await self._fetch_additional_data(state, "diff_content")

        # Truncate content to prevent token limits
        truncated_diff = self._truncate_content(state.diff_content, settings.max_diff_chars)
        
        prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessage(content=prompts.CHECK_LOGICAL_SECURITY_PROMPT),
                HumanMessage(
                    content=f"""Analyze this diff for logical security vulnerabilities:
            
            {truncated_diff}
            
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

    # async def _find_critical_bugs(
    #     self, state: ReviewState
    # ) -> ReviewState:
    #     """Find critical bugs and potential zero-days."""
    #     self.logger.info("Finding critical bugs", pr=state.review_data.pr_number)

    #     prompt = ChatPromptTemplate.from_messages(
    #         [
    #             SystemMessage(content=prompts.FIND_CRITICAL_BUGS_PROMPT),
    #             HumanMessage(
    #                 content=f"""Hunt for critical bugs in this code change:
            
    #         {state.diff_content}
            
    #         Focus on exploitable vulnerabilities and critical system failures."""
    #             ),
    #         ]
    #     )

    #     try:
    #         chain = prompt | self.llm | JsonOutputParser()
    #         response = await chain.ainvoke({})

    #         findings = self._parse_ai_response(response, "critical_bug")
    #         state.findings.extend(findings)

    #         self.logger.info(
    #             "Critical bug analysis completed",
    #             findings_count=len(findings),
    #             pr=state.review_data.pr_number,
    #         )

    #     except Exception as e:
    #         self.logger.error("Bug hunting failed", error=str(e))

    #     state.current_step = "bugs_complete"
    #     return state

    # async def _review_naming_conventions(
    #     self, state: ReviewState
    # ) -> ReviewState:
    #     """Review naming conventions that impact readability."""
    #     self.logger.info("Reviewing naming conventions", pr=state.review_data.pr_number)

    #     prompt = ChatPromptTemplate.from_messages(
    #         [
    #             SystemMessage(content=prompts.REVIEW_NAMING_CONVENTIONS_PROMPT),
    #             HumanMessage(
    #                 content=f"""Review naming in this code change:
            
    #         {state.diff_content}
            
    #         Focus on clarity, domain appropriateness, and maintainability."""
    #             ),
    #         ]
    #     )

    #     try:
    #         chain = prompt | self.llm | JsonOutputParser()
    #         response = await chain.ainvoke({})

    #         findings = self._parse_ai_response(response, "naming")
    #         state.findings.extend(findings)

    #         self.logger.info(
    #             "Naming review completed",
    #             findings_count=len(findings),
    #             pr=state.review_data.pr_number,
    #         )

    #     except Exception as e:
    #         self.logger.error("Naming review failed", error=str(e))

    #     state.current_step = "naming_complete"
    #     return state

    # async def _check_code_optimization(
    #     self, state: ReviewState
    # ) -> ReviewState:
    #     """Check for code optimization opportunities."""
    #     self.logger.info(
    #         "Checking optimization opportunities", pr=state.review_data.pr_number
    #     )

    #     prompt = ChatPromptTemplate.from_messages(
    #         [
    #             SystemMessage(content=prompts.CHECK_CODE_OPTIMIZATION_PROMPT),
    #             HumanMessage(
    #                 content=f"""Analyze optimization opportunities in:
            
    #         {state.diff_content}
            
    #         Consider the application context and user impact."""
    #             ),
    #         ]
    #     )

    #     try:
    #         chain = prompt | self.llm | JsonOutputParser()
    #         response = await chain.ainvoke({})

    #         findings = self._parse_ai_response(response, "optimization")
    #         state.findings.extend(findings)

    #         self.logger.info(
    #             "Optimization analysis completed",
    #             findings_count=len(findings),
    #             pr=state.review_data.pr_number,
    #         )

    #     except Exception as e:
    #         self.logger.error("Optimization analysis failed", error=str(e))

    #     state.current_step = "optimization_complete"
    #     return state

    # async def _verify_design_principles(
    #     self, state: ReviewState
    # ) -> ReviewState:
    #     """Verify adherence to DRY and KISS principles."""
    #     self.logger.info("Verifying design principles", pr=state.review_data.pr_number)

    #     prompt = ChatPromptTemplate.from_messages(
    #         [
    #             SystemMessage(content=prompts.VERIFY_DESIGN_PRINCIPLES_PROMPT),
    #             HumanMessage(
    #                 content=f"""Evaluate design principle adherence in:
            
    #         {state.diff_content}
            
    #         Suggest concrete refactoring improvements."""
    #             ),
    #         ]
    #     )

    #     try:
    #         chain = prompt | self.llm | JsonOutputParser()
    #         response = await chain.ainvoke({})

    #         findings = self._parse_ai_response(response, "principles")
    #         state.findings.extend(findings)

    #         self.logger.info(
    #             "Design principles analysis completed",
    #             findings_count=len(findings),
    #             pr=state.review_data.pr_number,
    #         )

    #     except Exception as e:
    #         self.logger.error("Design principles analysis failed", error=str(e))

    #     state.current_step = "principles_complete"
    #     return state

    async def _generate_review_summary(
        self, state: ReviewState
    ) -> ReviewState:
        """Generate simple review summary."""
        self.logger.info("Generating review summary", pr=state.review_data.pr_number)

        # Group findings by severity
        critical_findings = [f for f in state.findings if f.severity == "critical"]
        high_findings = [f for f in state.findings if f.severity == "high"]
        medium_findings = [f for f in state.findings if f.severity == "medium"]

        # Determine recommendation
        if critical_findings:
            recommendation = "request_changes"
        elif len(high_findings) >= 3:
            recommendation = "request_changes"
        elif high_findings or len(medium_findings) >= 5:
            recommendation = "comment"
        else:
            recommendation = "approve"

        # Enhanced summary generation
        total_findings = len(state.findings)
        if total_findings == 0:
            summary = "✅ **Review Complete**: This PR looks good! No significant logic, security, or critical issues found during analysis."
        else:
            # Create context-aware summary
            if critical_findings:
                summary = f"🚨 **Critical Issues Found**: This PR requires immediate attention before merging. Found {len(critical_findings)} critical security/logic issue(s) that could impact system reliability."
            elif len(high_findings) >= 3:
                summary = f"⚠️ **Multiple High-Priority Issues**: This PR has {len(high_findings)} high-severity issues that should be addressed before merging to maintain code quality."
            elif high_findings:
                summary = f"📋 **Issues Identified**: Found {len(high_findings)} high-priority and {len(medium_findings)} medium-priority issues. Please review the suggestions below."
            elif len(medium_findings) >= 5:
                summary = f"📝 **Several Improvements Suggested**: Found {len(medium_findings)} medium-priority improvements that would enhance code quality and maintainability."
            else:
                summary = f"🔍 **Minor Issues Found**: Found {total_findings} minor issue(s). Consider addressing these for improved code quality."

        # Store final results
        state.current_step = "complete"
        state.review_summary = summary
        state.review_comments = []  # Simplified - no detailed comments for now
        state.recommendation = recommendation

        return state

    async def review_pull_request(
        self,
        review_data: ReviewData,
        diff_content: str = "",
        file_contents: dict[str, str] | None = None,
        project_structure: dict | None = None,
    ) -> dict:
        """Perform comprehensive logical review of a pull request."""
        self.logger.info(
            "Starting logical review",
            repo=review_data.repository,
            pr=review_data.pr_number,
        )

        try:
            # Initialize state with minimal data - additional data fetched on demand
            state = ReviewState(
                review_data=review_data,
                diff_content=diff_content,
                file_contents=file_contents or {},
                project_structure=project_structure or {},
                mcp_analyzer=self.mcp_analyzer,
            )

            # Run review workflow
            final_state_result = await self.review_graph.ainvoke(state)

            # Handle both dict and ReviewState objects
            if isinstance(final_state_result, dict):
                # Convert dict back to ReviewState if needed
                findings = final_state_result.get("findings", [])
                review_summary = final_state_result.get("review_summary", "Review completed")
                recommendation = final_state_result.get("recommendation", "comment")
                review_comments = final_state_result.get("review_comments", [])
            else:
                # Use object attributes directly
                findings = final_state_result.findings
                review_summary = final_state_result.review_summary
                recommendation = final_state_result.recommendation
                review_comments = final_state_result.review_comments

            # Helper function to safely get severity
            def get_severity(finding):
                if hasattr(finding, 'severity'):
                    return finding.severity
                elif isinstance(finding, dict):
                    return finding.get('severity', 'medium')
                else:
                    return 'medium'

            # Return minimal structure for GitHub posting
            total_findings = len(findings)
            critical_count = len([f for f in findings if get_severity(f) == "critical"])
            high_count = len([f for f in findings if get_severity(f) == "high"])
            medium_count = len([f for f in findings if get_severity(f) == "medium"])
            low_count = len([f for f in findings if get_severity(f) == "low"])
            
            return {
                "summary": review_summary,
                "recommendation": recommendation,
                "comments": review_comments,
                "total_findings": total_findings,
                "critical_count": critical_count,
                "high_count": high_count,
                "medium_count": medium_count,
                "low_count": low_count,
            }
            # return {
            #     "repository": final_state.review_data.repository,
            #     "pr_number": final_state.review_data.pr_number,
            #     "findings": [finding.model_dump() for finding in final_state.findings],
            #     "summary": final_state.review_summary,
            #     "recommendation": final_state.recommendation,
            #     "comments": final_state.review_comments,
            #     "critical_count": len(
            #         [f for f in final_state.findings if f.severity == "critical"]
            #     ),
            #     "high_count": len(
            #         [f for f in final_state.findings if f.severity == "high"]
            #     ),
            #     "medium_count": len(
            #         [f for f in final_state.findings if f.severity == "medium"]
            #     ),
            #     "low_count": len(
            #         [f for f in final_state.findings if f.severity == "low"]
            #     ),
            #     "total_findings": len(final_state.findings),
            #     "error": final_state.error,
            # }

        except Exception as e:
            self.logger.error("Logical review failed", error=str(e))
            return {
                "summary": f"Review failed: {e}",
                "recommendation": "comment",
                "comments": [],
                "total_findings": 0,
                "critical_count": 0,
                "high_count": 0,
                "medium_count": 0,
                "low_count": 0,
            }
