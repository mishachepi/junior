"""Main review agent orchestrating modular components for code review."""

import structlog
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from ..config import settings
from ..models import ReviewData
from .tools import RepositoryAnalyzer
from .react_agent import ReactAgent
from .review_logic import ReviewLogic
from .review_utils import ReviewState, get_severity_counts

logger = structlog.get_logger(__name__)


class ReviewAgent:
    """Main review agent orchestrating modular components for code review."""

    def __init__(self, use_react: bool = True):
        self.logger = logger.bind(component="ReviewAgent")
        self.use_react = use_react
        self._setup_llm()
        self.mcp_analyzer = RepositoryAnalyzer()
        
        # Initialize modular components
        self.react_agent = ReactAgent(self.llm) if settings.enable_react_agent else None
        self.review_logic = ReviewLogic(self.llm, self.react_agent)
        
        self._setup_review_graph(use_react)

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

    def _setup_review_graph(self, use_react: bool = True) -> None:
        """Set up specialized review workflow with configurable analysis mode."""
        workflow = StateGraph(ReviewState)

        # Create wrapper functions with is_react parameter
        async def analyze_logic_wrapper(state):
            return await self.review_logic.analyze_project_logic(state, is_react=use_react)
        
        async def check_security_wrapper(state):
            return await self.review_logic.check_logical_security(state, is_react=use_react)
        
        async def find_bugs_wrapper(state):
            return await self.review_logic.find_critical_bugs(state, is_react=use_react)
        
        async def review_naming_wrapper(state):
            return await self.review_logic.review_naming_conventions(state, is_react=use_react)
        
        async def check_optimization_wrapper(state):
            return await self.review_logic.check_code_optimization(state, is_react=use_react)
        
        async def verify_principles_wrapper(state):
            return await self.review_logic.verify_design_principles(state, is_react=use_react)

        # Add review steps with wrapper functions
        workflow.add_node("analyze_logic", analyze_logic_wrapper)
        workflow.add_node("check_security", check_security_wrapper)
        workflow.add_node("find_critical_bugs", find_bugs_wrapper)
        workflow.add_node("review_naming", review_naming_wrapper)
        workflow.add_node("check_optimization", check_optimization_wrapper)
        workflow.add_node("verify_principles", verify_principles_wrapper)
        workflow.add_node("generate_summary", self.review_logic.generate_review_summary_step)

        # Set entry point
        workflow.set_entry_point("analyze_logic")

        # Define complete workflow
        workflow.add_edge("analyze_logic", "check_security")
        workflow.add_edge("check_security", "find_critical_bugs")
        workflow.add_edge("find_critical_bugs", "review_naming")
        workflow.add_edge("review_naming", "check_optimization")
        workflow.add_edge("check_optimization", "verify_principles")
        workflow.add_edge("verify_principles", "generate_summary")
        workflow.add_edge("generate_summary", END)

        self.review_graph = workflow.compile()

    def switch_mode(self, use_react: bool) -> None:
        """Switch between ReAct and Simple analysis modes."""
        if self.use_react != use_react:
            self.use_react = use_react
            self.logger.info("Switching analysis mode", new_mode="ReAct" if use_react else "Simple")
            self._setup_review_graph(use_react)

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
            analysis_mode="ReAct" if self.use_react else "Simple",
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

            # Get severity counts and return results
            severity_counts = get_severity_counts(findings)
            
            return {
                "summary": review_summary,
                "recommendation": recommendation,
                "comments": review_comments,
                **severity_counts
            }

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