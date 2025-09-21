"""ReAct agent for dynamic repository analysis during code reviews."""

import structlog
from langchain.agents import create_react_agent, AgentExecutor
from langchain.prompts import PromptTemplate

from ..config import settings
from .mcp_tools import create_mcp_tools
from .review_utils import ReviewFinding

logger = structlog.get_logger(__name__)


class ReactAgent:
    """ReAct agent for dynamic code analysis using MCP tools."""
    
    def __init__(self, llm):
        self.llm = llm
        self.logger = logger.bind(component="ReactAgent")
        
    def setup_agent(self, file_contents: dict, project_structure: dict) -> AgentExecutor | None:
        """Set up ReAct agent with MCP tools for dynamic analysis."""
        try:
            # Only setup if we have repository data
            if not file_contents and not project_structure:
                return None
                
            # Create MCP tools using the repository data
            mcp_tools = create_mcp_tools(
                file_contents=file_contents,
                project_structure=project_structure
            )
            
            # ReAct prompt template focused on code review
            react_prompt = PromptTemplate(
                input_variables=["tools", "tool_names", "input", "agent_scratchpad"],
                template="""You are an expert code reviewer with access to repository analysis tools.
Your job is to analyze code changes and provide specific, actionable feedback.

Available tools:
{tools}

Use this format for your analysis:

Question: {input}
Thought: I should analyze this systematically. What information do I need?
Action: [choose from {tool_names}]
Action Input: [specific parameters for the tool]
Observation: [tool result]
Thought: [analyze the observation and decide next steps]
... (repeat as needed, but be efficient - aim for 2-3 tool uses maximum)
Thought: I have enough information to provide my analysis
Final Answer: [detailed analysis with specific findings, line numbers, and recommendations]

Begin:
Question: {input}
{agent_scratchpad}"""
            )
            
            # Create ReAct agent
            agent = create_react_agent(
                llm=self.llm,
                tools=mcp_tools,
                prompt=react_prompt
            )
            
            # Create agent executor with configurable limits
            agent_executor = AgentExecutor(
                agent=agent,
                tools=mcp_tools,
                verbose=False,  # Set to True for debugging
                max_iterations=settings.react_agent_max_iterations,
                max_execution_time=settings.react_agent_timeout,
                handle_parsing_errors=True,
                return_intermediate_steps=True,
            )
            
            return agent_executor
            
        except Exception as e:
            self.logger.error("Failed to setup ReAct agent", error=str(e))
            return None

    async def analyze(self, agent_executor: AgentExecutor, query: str) -> dict:
        """Use ReAct agent to perform dynamic analysis for a specific query."""
        try:
            if not agent_executor:
                return {"analysis": "ReAct agent not available", "findings": []}
            
            # Run the agent
            self.logger.info("Running ReAct agent", query=query[:100])
            result = await agent_executor.ainvoke({"input": query})
            
            # Parse the result
            analysis = result.get("output", "")
            intermediate_steps = result.get("intermediate_steps", [])
            
            # Log the steps for debugging
            for i, (action, observation) in enumerate(intermediate_steps):
                self.logger.debug(
                    "ReAct step", 
                    step=i+1, 
                    action=action.tool, 
                    observation_length=len(str(observation))
                )
            
            return {
                "analysis": analysis,
                "tool_steps": len(intermediate_steps),
                "findings": []  # Will be parsed from analysis if needed
            }
            
        except Exception as e:
            self.logger.error("ReAct agent execution failed", query=query[:50], error=str(e))
            return {"analysis": f"Analysis failed: {str(e)}", "findings": []}

    def parse_analysis(self, analysis: str, category: str) -> list[ReviewFinding]:
        """Parse ReAct agent analysis into detailed ReviewFinding objects."""
        findings = []
        
        try:
            lines = analysis.split('\n')
            current_context = []
            
            for i, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue
                
                # Track context for better understanding
                current_context.append(line)
                if len(current_context) > 3:
                    current_context.pop(0)
                
                # Enhanced file path parsing with context
                if self._contains_file_reference(line):
                    file_path, line_num, context_message = self._extract_file_info(line, current_context)
                    if file_path:
                        severity = self._determine_severity_from_context(context_message, category)
                        suggestion = self._generate_specific_suggestion(context_message, category)
                        
                        finding = ReviewFinding(
                            category=category,
                            severity=severity,
                            message=f"**{category.title()} Issue in {file_path}**: {context_message}",
                            file_path=file_path,
                            line_number=line_num,
                            suggestion=suggestion
                        )
                        findings.append(finding)
                
                # Look for specific patterns and create targeted findings
                elif self._contains_security_concern(line):
                    finding = self._create_security_finding(line, category, current_context)
                    if finding:
                        findings.append(finding)
                
                elif self._contains_performance_issue(line):
                    finding = self._create_performance_finding(line, category, current_context)
                    if finding:
                        findings.append(finding)
                
                elif self._contains_logic_issue(line):
                    finding = self._create_logic_finding(line, category, current_context)
                    if finding:
                        findings.append(finding)
            
            # Extract key insights if no specific findings were parsed
            if not findings and analysis:
                insights = self._extract_key_insights(analysis, category)
                findings.extend(insights)
                
        except Exception as e:
            self.logger.error("Failed to parse ReAct analysis", error=str(e))
            
        return findings

    def _contains_file_reference(self, line: str) -> bool:
        """Check if line contains a file reference."""
        return ':' in line and any(ext in line for ext in ['.py', '.js', '.ts', '.java', '.go', '.cpp', '.c', '.rb'])

    def _extract_file_info(self, line: str, context: list) -> tuple[str | None, int | None, str]:
        """Extract file path, line number, and context message."""
        try:
            if ':' in line:
                parts = line.split(':')
                file_path = parts[0].strip()
                
                # Try to parse line number
                line_num = None
                if len(parts) > 1:
                    try:
                        line_num = int(parts[1].strip().split()[0])
                    except (ValueError, IndexError):
                        pass
                
                # Build context message from surrounding lines
                context_message = ' '.join(context[-2:]) if len(context) >= 2 else line
                
                return file_path, line_num, context_message
        except Exception:
            pass
        return None, None, line

    def _determine_severity_from_context(self, message: str, category: str) -> str:
        """Determine severity based on message content and category."""
        message_lower = message.lower()
        
        # Critical patterns
        if any(keyword in message_lower for keyword in [
            'vulnerability', 'exploit', 'injection', 'buffer overflow', 'race condition',
            'memory leak', 'deadlock', 'authentication bypass'
        ]):
            return "critical"
        
        # High severity patterns
        if any(keyword in message_lower for keyword in [
            'security', 'unsafe', 'dangerous', 'risk', 'error handling',
            'null pointer', 'undefined behavior', 'performance bottleneck'
        ]):
            return "high"
        
        # Medium for most other issues
        if any(keyword in message_lower for keyword in [
            'issue', 'problem', 'concern', 'improvement', 'inconsistent'
        ]):
            return "medium"
        
        return "low"

    def _generate_specific_suggestion(self, message: str, category: str) -> str:
        """Generate specific, actionable suggestions based on content."""
        message_lower = message.lower()
        
        # Security-specific suggestions
        if 'injection' in message_lower:
            return "Use parameterized queries or input validation to prevent injection attacks"
        elif 'authentication' in message_lower:
            return "Review authentication logic and ensure proper session management"
        elif 'authorization' in message_lower:
            return "Verify permission checks and access control implementation"
        
        # Performance suggestions
        elif 'performance' in message_lower or 'optimization' in message_lower:
            return "Consider algorithm optimization, caching, or async processing"
        elif 'memory' in message_lower:
            return "Review memory usage patterns and implement proper cleanup"
        
        # Logic suggestions
        elif 'logic' in message_lower or 'condition' in message_lower:
            return "Review conditional logic and add edge case handling"
        elif 'error' in message_lower:
            return "Implement proper error handling and validation"
        
        # Naming suggestions
        elif category == 'naming':
            return "Consider more descriptive names that reflect business domain"
        
        # Generic suggestions by category
        suggestions = {
            'security': "Review for potential security vulnerabilities and add appropriate safeguards",
            'logic': "Analyze logic flow and ensure all edge cases are handled properly",
            'optimization': "Evaluate performance impact and consider optimization strategies",
            'critical_bug': "Investigate for potential runtime issues and add defensive checks",
            'principles': "Refactor to improve code maintainability and follow SOLID principles"
        }
        
        return suggestions.get(category, "Review implementation and consider the highlighted concern")

    def _contains_security_concern(self, line: str) -> bool:
        """Check for security-related concerns."""
        return any(keyword in line.lower() for keyword in [
            'security', 'vulnerable', 'exploit', 'attack', 'malicious', 'unsafe'
        ])

    def _contains_performance_issue(self, line: str) -> bool:
        """Check for performance-related issues."""
        return any(keyword in line.lower() for keyword in [
            'performance', 'slow', 'inefficient', 'bottleneck', 'optimization', 'memory'
        ])

    def _contains_logic_issue(self, line: str) -> bool:
        """Check for logic-related issues."""
        return any(keyword in line.lower() for keyword in [
            'logic', 'condition', 'edge case', 'error', 'exception', 'validation'
        ])

    def _create_security_finding(self, line: str, category: str, context: list) -> ReviewFinding | None:
        """Create a security-focused finding."""
        return ReviewFinding(
            category="security",
            severity="high",
            message=f"**Security Concern**: {line}",
            suggestion=self._generate_specific_suggestion(line, "security")
        )

    def _create_performance_finding(self, line: str, category: str, context: list) -> ReviewFinding | None:
        """Create a performance-focused finding."""
        return ReviewFinding(
            category="optimization",
            severity="medium",
            message=f"**Performance Issue**: {line}",
            suggestion=self._generate_specific_suggestion(line, "optimization")
        )

    def _create_logic_finding(self, line: str, category: str, context: list) -> ReviewFinding | None:
        """Create a logic-focused finding."""
        return ReviewFinding(
            category="logic",
            severity="medium",
            message=f"**Logic Concern**: {line}",
            suggestion=self._generate_specific_suggestion(line, "logic")
        )

    def _extract_key_insights(self, analysis: str, category: str) -> list[ReviewFinding]:
        """Extract key insights when no specific patterns match."""
        insights = []
        
        # Split into sentences and find meaningful insights
        sentences = [s.strip() for s in analysis.replace('\n', ' ').split('.') if s.strip()]
        
        for sentence in sentences[:3]:  # Limit to top 3 insights
            if len(sentence) > 20 and any(keyword in sentence.lower() for keyword in [
                'recommend', 'suggest', 'should', 'could', 'consider', 'improve'
            ]):
                finding = ReviewFinding(
                    category=category,
                    severity="low",
                    message=f"**ReAct Insight**: {sentence}",
                    suggestion="Consider this analysis finding for code improvement"
                )
                insights.append(finding)
        
        return insights