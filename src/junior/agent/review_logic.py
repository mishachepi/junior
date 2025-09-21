"""Predetermined workflow steps for code review analysis."""

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from ..config import settings
from . import prompts
from .review_utils import (
    ReviewState, 
    truncate_content, 
    fetch_additional_data, 
    parse_ai_response,
    generate_review_summary
)

logger = structlog.get_logger(__name__)


class ReviewLogic:
    """Predetermined workflow steps for code review analysis."""
    
    def __init__(self, llm, react_agent=None):
        self.llm = llm
        self.react_agent = react_agent
        self.logger = logger.bind(component="ReviewLogic")

    async def _enhanced_analysis_with_react(
        self, 
        state: ReviewState, 
        category: str, 
        react_query: str
    ) -> list:
        """Perform enhanced analysis using ReAct agent if enabled."""
        additional_findings = []
        
        if settings.enable_react_agent and state.file_contents and self.react_agent:
            try:
                # Setup ReAct agent if not already done
                if not state.agent_executor:
                    state.agent_executor = self.react_agent.setup_agent(
                        state.file_contents, 
                        state.project_structure
                    )
                
                if state.agent_executor:
                    react_result = await self.react_agent.analyze(state.agent_executor, react_query)
                    if react_result.get("analysis"):
                        additional_findings = self.react_agent.parse_analysis(
                            react_result["analysis"], 
                            category
                        )
                        
                        self.logger.info(
                            f"ReAct {category} analysis completed",
                            additional_findings=len(additional_findings),
                            tool_steps=react_result.get("tool_steps", 0)
                        )
                        
            except Exception as e:
                self.logger.error(f"ReAct {category} analysis failed", error=str(e))
        
        return additional_findings

    async def _react_only_analysis(self, state: ReviewState, category: str, query_template: str) -> list:
        """Perform ReAct-only analysis without traditional LLM call."""
        findings = []
        
        if settings.enable_react_agent and self.react_agent:
            try:
                # Setup ReAct agent if not already done
                if not state.agent_executor:
                    state.agent_executor = self.react_agent.setup_agent(
                        state.file_contents, 
                        state.project_structure
                    )
                
                if state.agent_executor:
                    # Format query with state data
                    react_query = query_template.format(
                        repository=state.review_data.repository,
                        pr_number=state.review_data.pr_number,
                        title=state.review_data.title
                    )
                    
                    react_result = await self.react_agent.analyze(state.agent_executor, react_query)
                    if react_result.get("analysis"):
                        findings = self.react_agent.parse_analysis(
                            react_result["analysis"], 
                            category
                        )
                        
                        self.logger.info(
                            f"ReAct-only {category} analysis completed",
                            findings_count=len(findings),
                            tool_steps=react_result.get("tool_steps", 0)
                        )
                        
            except Exception as e:
                self.logger.error(f"ReAct-only {category} analysis failed", error=str(e))
        
        return findings

    async def analyze_project_logic(self, state: ReviewState, is_react: bool = True) -> ReviewState:
        """Analyze overall project logic and architecture."""
        analysis_mode = "ReAct" if is_react else "Simple"
        self.logger.info("Analyzing project logic", pr=state.review_data.pr_number, mode=analysis_mode)

        # Fetch data on demand
        if not state.diff_content:
            await fetch_additional_data(state, "diff_content", state.mcp_analyzer)
        if not state.project_structure:
            await fetch_additional_data(state, "project_structure", state.mcp_analyzer)

        try:
            if is_react and settings.enable_react_agent and self.react_agent:
                # ReAct-only analysis
                findings = await self._react_only_analysis(state, "logic", """
                Perform comprehensive logic analysis on this PR:
                
                Repository: {repository}
                PR #{pr_number}: {title}
                
                Focus on:
                1. Control flow logic in changed files
                2. Function definitions and their logic
                3. Conditional statements and edge cases
                4. Integration points with other parts of the codebase
                5. Business logic validation and consistency
                
                Use available tools to examine specific files and their relationships.
                Provide concrete findings with file paths and line numbers where possible.
                """)
                state.findings.extend(findings)
                
                self.logger.info(
                    "ReAct logic analysis completed",
                    findings_count=len(findings),
                    pr=state.review_data.pr_number,
                )
            else:
                # Simple analysis
                truncated_diff = truncate_content(state.diff_content, settings.max_diff_chars)
                truncated_structure = truncate_content(str(state.project_structure), settings.max_structure_chars)
                
                prompt = ChatPromptTemplate.from_messages([
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
                ])

                chain = prompt | self.llm | JsonOutputParser()
                response = await chain.ainvoke({})

                findings = parse_ai_response(response, "logic")
                state.findings.extend(findings)

                self.logger.info(
                    "Simple logic analysis completed",
                    findings_count=len(findings),
                    pr=state.review_data.pr_number,
                )

        except Exception as e:
            self.logger.error("Logic analysis failed", error=str(e), mode=analysis_mode)
            state.error = f"Logic analysis failed: {e}"

        state.current_step = "logic_complete"
        return state

    async def check_logical_security(self, state: ReviewState, is_react: bool = True) -> ReviewState:
        """Check for logical security vulnerabilities."""
        analysis_mode = "ReAct" if is_react else "Simple"
        self.logger.info("Checking logical security", pr=state.review_data.pr_number, mode=analysis_mode)

        # Ensure diff content is available
        if not state.diff_content:
            await fetch_additional_data(state, "diff_content", state.mcp_analyzer)

        try:
            if is_react and settings.enable_react_agent and self.react_agent:
                # ReAct-only analysis
                findings = await self._react_only_analysis(state, "security", """
                Perform comprehensive security analysis on this PR:
                
                Repository: {repository}
                PR #{pr_number}: {title}
                
                Security focus areas:
                1. Authentication and authorization logic
                2. Input validation and sanitization
                3. SQL injection and XSS vulnerabilities
                4. Secret management and API keys
                5. Access control and permission checks
                6. Data exposure and information leakage
                
                Use available tools to:
                - Analyze files with security focus
                - Search for security-related patterns
                - Check related files for security context
                
                Provide specific security findings with file paths and line numbers.
                """)
                state.findings.extend(findings)
                
                self.logger.info(
                    "ReAct security analysis completed",
                    findings_count=len(findings),
                    pr=state.review_data.pr_number,
                )
            else:
                # Simple security analysis
                truncated_diff = truncate_content(state.diff_content, settings.max_diff_chars)
                
                prompt = ChatPromptTemplate.from_messages([
                    SystemMessage(content=prompts.CHECK_LOGICAL_SECURITY_PROMPT),
                    HumanMessage(
                        content=f"""Analyze this diff for logical security vulnerabilities:
                
                {truncated_diff}
                
                Consider the broader application context and potential attack scenarios."""
                    ),
                ])

                chain = prompt | self.llm | JsonOutputParser()
                response = await chain.ainvoke({})

                findings = parse_ai_response(response, "security")
                state.findings.extend(findings)

                self.logger.info(
                    "Simple security analysis completed",
                    findings_count=len(findings),
                    pr=state.review_data.pr_number,
                )

        except Exception as e:
            self.logger.error("Security analysis failed", error=str(e), mode=analysis_mode)

        state.current_step = "security_complete"
        return state

    async def find_critical_bugs(self, state: ReviewState, is_react: bool = True) -> ReviewState:
        """Find critical bugs and potential zero-days."""
        analysis_mode = "ReAct" if is_react else "Simple"
        self.logger.info("Finding critical bugs", pr=state.review_data.pr_number, mode=analysis_mode)

        # Ensure diff content is available
        if not state.diff_content:
            await fetch_additional_data(state, "diff_content", state.mcp_analyzer)

        try:
            if is_react and settings.enable_react_agent and self.react_agent:
                # ReAct-only analysis
                findings = await self._react_only_analysis(state, "critical_bug", """
                Hunt for critical bugs and exploitable vulnerabilities in this PR:
                
                Repository: {repository}
                PR #{pr_number}: {title}
                
                Focus on:
                1. Memory safety issues and buffer overflows
                2. Race conditions and concurrency bugs  
                3. Logic bombs and backdoors
                4. Input validation bypasses
                5. Resource exhaustion vulnerabilities
                
                Use available tools to examine specific files and search for dangerous patterns.
                Provide concrete findings with file paths and line numbers.
                """)
                state.findings.extend(findings)
                
                self.logger.info(
                    "ReAct critical bug analysis completed",
                    findings_count=len(findings),
                    pr=state.review_data.pr_number,
                )
            else:
                # Simple critical bug analysis
                truncated_diff = truncate_content(state.diff_content, settings.max_diff_chars)
                
                prompt = ChatPromptTemplate.from_messages([
                    SystemMessage(content=prompts.FIND_CRITICAL_BUGS_PROMPT),
                    HumanMessage(
                        content=f"""Hunt for critical bugs in this code change:
                
                {truncated_diff}
                
                Focus on exploitable vulnerabilities and critical system failures."""
                    ),
                ])

                chain = prompt | self.llm | JsonOutputParser()
                response = await chain.ainvoke({})

                findings = parse_ai_response(response, "critical_bug")
                state.findings.extend(findings)

                self.logger.info(
                    "Simple critical bug analysis completed",
                    findings_count=len(findings),
                    pr=state.review_data.pr_number,
                )

        except Exception as e:
            self.logger.error("Bug hunting failed", error=str(e), mode=analysis_mode)

        state.current_step = "bugs_complete"
        return state

    async def review_naming_conventions(self, state: ReviewState, is_react: bool = True) -> ReviewState:
        """Review naming conventions that impact readability."""
        analysis_mode = "ReAct" if is_react else "Simple"
        self.logger.info("Reviewing naming conventions", pr=state.review_data.pr_number, mode=analysis_mode)

        # Ensure diff content is available
        if not state.diff_content:
            await fetch_additional_data(state, "diff_content", state.mcp_analyzer)

        try:
            if is_react and settings.enable_react_agent and self.react_agent:
                # ReAct-only analysis
                findings = await self._react_only_analysis(state, "naming", """
                Review naming conventions and readability in this PR:
                
                Repository: {repository}
                PR #{pr_number}: {title}
                
                Focus on:
                1. Function and variable naming clarity
                2. Domain-appropriate terminology
                3. Consistency with existing codebase
                4. Misleading or confusing names
                5. Names that don't reflect actual functionality
                
                Use available tools to analyze function definitions and search for naming patterns.
                Provide specific suggestions for improvement with file paths and line numbers.
                """)
                state.findings.extend(findings)
                
                self.logger.info(
                    "ReAct naming review completed",
                    findings_count=len(findings),
                    pr=state.review_data.pr_number,
                )
            else:
                # Simple naming analysis
                truncated_diff = truncate_content(state.diff_content, settings.max_diff_chars)
                
                prompt = ChatPromptTemplate.from_messages([
                    SystemMessage(content=prompts.REVIEW_NAMING_CONVENTIONS_PROMPT),
                    HumanMessage(
                        content=f"""Review naming in this code change:
                
                {truncated_diff}
                
                Focus on clarity, domain appropriateness, and maintainability."""
                    ),
                ])

                chain = prompt | self.llm | JsonOutputParser()
                response = await chain.ainvoke({})

                findings = parse_ai_response(response, "naming")
                state.findings.extend(findings)

                self.logger.info(
                    "Simple naming review completed",
                    findings_count=len(findings),
                    pr=state.review_data.pr_number,
                )

        except Exception as e:
            self.logger.error("Naming review failed", error=str(e), mode=analysis_mode)

        state.current_step = "naming_complete"
        return state

    async def check_code_optimization(self, state: ReviewState, is_react: bool = True) -> ReviewState:
        """Check for code optimization opportunities."""
        analysis_mode = "ReAct" if is_react else "Simple"
        self.logger.info(
            "Checking optimization opportunities", pr=state.review_data.pr_number, mode=analysis_mode
        )

        # Ensure diff content is available
        if not state.diff_content:
            await fetch_additional_data(state, "diff_content", state.mcp_analyzer)

        try:
            if is_react and settings.enable_react_agent and self.react_agent:
                # ReAct-only analysis
                findings = await self._react_only_analysis(state, "optimization", """
                Analyze performance and optimization opportunities in this PR:
                
                Repository: {repository}
                PR #{pr_number}: {title}
                
                Focus on:
                1. Algorithm efficiency and complexity
                2. Database query optimization
                3. Caching opportunities
                4. Unnecessary computations or loops
                5. Memory usage patterns
                6. Network call efficiency
                
                Use available tools to analyze performance-critical code sections and search for optimization patterns.
                Provide specific recommendations with file paths and line numbers.
                """)
                state.findings.extend(findings)
                
                self.logger.info(
                    "ReAct optimization analysis completed",
                    findings_count=len(findings),
                    pr=state.review_data.pr_number,
                )
            else:
                # Simple optimization analysis
                truncated_diff = truncate_content(state.diff_content, settings.max_diff_chars)
                
                prompt = ChatPromptTemplate.from_messages([
                    SystemMessage(content=prompts.CHECK_CODE_OPTIMIZATION_PROMPT),
                    HumanMessage(
                        content=f"""Analyze optimization opportunities in:
                
                {truncated_diff}
                
                Consider the application context and user impact."""
                    ),
                ])

                chain = prompt | self.llm | JsonOutputParser()
                response = await chain.ainvoke({})

                findings = parse_ai_response(response, "optimization")
                state.findings.extend(findings)

                self.logger.info(
                    "Simple optimization analysis completed",
                    findings_count=len(findings),
                    pr=state.review_data.pr_number,
                )

        except Exception as e:
            self.logger.error("Optimization analysis failed", error=str(e), mode=analysis_mode)

        state.current_step = "optimization_complete"
        return state

    async def verify_design_principles(self, state: ReviewState, is_react: bool = True) -> ReviewState:
        """Verify adherence to DRY and KISS principles."""
        analysis_mode = "ReAct" if is_react else "Simple"
        self.logger.info("Verifying design principles", pr=state.review_data.pr_number, mode=analysis_mode)

        # Ensure diff content is available
        if not state.diff_content:
            await fetch_additional_data(state, "diff_content", state.mcp_analyzer)

        try:
            if is_react and settings.enable_react_agent and self.react_agent:
                # ReAct-only analysis
                findings = await self._react_only_analysis(state, "principles", """
                Evaluate design principle adherence in this PR:
                
                Repository: {repository}
                PR #{pr_number}: {title}
                
                Focus on:
                1. DRY (Don't Repeat Yourself) violations
                2. KISS (Keep It Simple Stupid) violations
                3. Single Responsibility Principle
                4. Code duplication opportunities
                5. Over-engineering or unnecessary complexity
                6. Refactoring opportunities
                
                Use available tools to search for similar code patterns and analyze function complexity.
                Suggest concrete refactoring improvements with file paths and line numbers.
                """)
                state.findings.extend(findings)
                
                self.logger.info(
                    "ReAct design principles analysis completed",
                    findings_count=len(findings),
                    pr=state.review_data.pr_number,
                )
            else:
                # Simple design principles analysis
                truncated_diff = truncate_content(state.diff_content, settings.max_diff_chars)
                
                prompt = ChatPromptTemplate.from_messages([
                    SystemMessage(content=prompts.VERIFY_DESIGN_PRINCIPLES_PROMPT),
                    HumanMessage(
                        content=f"""Evaluate design principle adherence in:
                
                {truncated_diff}
                
                Suggest concrete refactoring improvements."""
                    ),
                ])

                chain = prompt | self.llm | JsonOutputParser()
                response = await chain.ainvoke({})

                findings = parse_ai_response(response, "principles")
                state.findings.extend(findings)

                self.logger.info(
                    "Simple design principles analysis completed",
                    findings_count=len(findings),
                    pr=state.review_data.pr_number,
                )

        except Exception as e:
            self.logger.error("Design principles analysis failed", error=str(e), mode=analysis_mode)

        state.current_step = "principles_complete"
        return state

    async def generate_review_summary_step(self, state: ReviewState) -> ReviewState:
        """Generate simple review summary."""
        self.logger.info("Generating review summary", pr=state.review_data.pr_number)

        # Generate summary and recommendation
        summary, recommendation = generate_review_summary(state.findings)

        # Store final results
        state.current_step = "complete"
        state.review_summary = summary
        state.review_comments = []  # Simplified - no detailed comments for now
        state.recommendation = recommendation

        return state