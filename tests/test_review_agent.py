"""Tests for the logical review agent."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from junior.agent import LogicalReviewState, ReviewAgent, ReviewFinding
from junior.models import ReviewData


class TestReviewAgent:
    """Tests for ReviewAgent."""

    @pytest.fixture
    def review_agent(self, monkeypatch):
        """Create review agent with mocked dependencies."""
        from junior.config import Settings
        test_settings = Settings(
            openai_api_key="test-key",
            github_token="test-token",
            secret_key="test-secret"
        )
        monkeypatch.setattr("junior.agent.review_agent.settings", test_settings)

        with patch("junior.agent.review_agent.ChatOpenAI"):
            agent = ReviewAgent()
            agent.llm = MagicMock()
            agent.llm.ainvoke = AsyncMock()
            return agent

    @pytest.fixture
    def sample_review_data(self):
        """Sample review data for testing."""
        return ReviewData(
            repository="test/repo",
            pr_number=123,
            title="Test PR",
            description="Test PR description",
            author="testuser",
            base_branch="main",
            head_branch="feature",
            base_sha="abc123",
            head_sha="def456",
            diff_url="https://github.com/test/repo/pull/123.diff",
            clone_url="https://github.com/test/repo.git"
        )

    @pytest.fixture
    def sample_state(self, sample_review_data):
        """Sample review state for testing."""
        return LogicalReviewState(
            review_data=sample_review_data,
            diff_content="@@ -1,3 +1,3 @@\n def test():\n-    print('old')\n+    print('new')",
            file_contents={"test.py": "def test():\n    print('new')"},
            project_structure={"project_type": "python", "main_language": "python"}
        )

    @pytest.mark.asyncio
    async def test_analyze_project_logic(self, review_agent, sample_state):
        """Test project logic analysis."""
        # Mock LLM response
        review_agent.llm.ainvoke.return_value = {
            "findings": [
                {
                    "category": "logic",
                    "severity": "high",
                    "message": "Missing null check",
                    "file_path": "test.py",
                    "line_number": 5,
                    "suggestion": "Add null validation"
                }
            ]
        }

        result_state = await review_agent._analyze_project_logic(sample_state)

        assert result_state.current_step == "logic_complete"
        assert len(result_state.findings) == 1
        assert result_state.findings[0].category == "logic"
        assert result_state.findings[0].severity == "high"

    @pytest.mark.asyncio
    async def test_analyze_project_logic_error(self, review_agent, sample_state):
        """Test project logic analysis with error."""
        # Mock LLM to raise exception
        review_agent.llm.ainvoke.side_effect = Exception("AI service error")

        result_state = await review_agent._analyze_project_logic(sample_state)

        assert result_state.error is not None
        assert "Logic analysis failed" in result_state.error

    @pytest.mark.asyncio
    async def test_check_logical_security(self, review_agent, sample_state):
        """Test logical security analysis."""
        review_agent.llm.ainvoke.return_value = {
            "findings": [
                {
                    "category": "security",
                    "severity": "critical",
                    "message": "Authentication bypass possible",
                    "file_path": "auth.py",
                    "suggestion": "Add proper authorization checks"
                }
            ]
        }

        result_state = await review_agent._check_logical_security(sample_state)

        assert result_state.current_step == "security_complete"
        assert len(result_state.findings) == 1
        assert result_state.findings[0].severity == "critical"

    @pytest.mark.asyncio
    async def test_find_critical_bugs(self, review_agent, sample_state):
        """Test critical bug detection."""
        review_agent.llm.ainvoke.return_value = {
            "findings": [
                {
                    "category": "critical_bug",
                    "severity": "critical",
                    "message": "Buffer overflow vulnerability",
                    "file_path": "buffer.c",
                    "line_number": 42
                }
            ]
        }

        result_state = await review_agent._find_critical_bugs(sample_state)

        assert result_state.current_step == "bugs_complete"
        assert len(result_state.findings) == 1
        assert result_state.findings[0].category == "critical_bug"

    @pytest.mark.asyncio
    async def test_review_naming_conventions(self, review_agent, sample_state):
        """Test naming convention review."""
        review_agent.llm.ainvoke.return_value = {
            "findings": [
                {
                    "category": "naming",
                    "severity": "medium",
                    "message": "Variable name is not descriptive",
                    "file_path": "calc.py",
                    "line_number": 10,
                    "suggestion": "Use more descriptive variable names"
                }
            ]
        }

        result_state = await review_agent._review_naming_conventions(sample_state)

        assert result_state.current_step == "naming_complete"
        assert len(result_state.findings) == 1
        assert result_state.findings[0].category == "naming"

    @pytest.mark.asyncio
    async def test_check_code_optimization(self, review_agent, sample_state):
        """Test code optimization analysis."""
        review_agent.llm.ainvoke.return_value = {
            "findings": [
                {
                    "category": "optimization",
                    "severity": "medium",
                    "message": "Inefficient loop detected",
                    "file_path": "loop.py",
                    "suggestion": "Consider using list comprehension"
                }
            ]
        }

        result_state = await review_agent._check_code_optimization(sample_state)

        assert result_state.current_step == "optimization_complete"
        assert len(result_state.findings) == 1
        assert result_state.findings[0].category == "optimization"

    @pytest.mark.asyncio
    async def test_verify_design_principles(self, review_agent, sample_state):
        """Test design principles verification."""
        review_agent.llm.ainvoke.return_value = {
            "findings": [
                {
                    "category": "principles",
                    "severity": "high",
                    "message": "DRY principle violation",
                    "principle_violated": "DRY",
                    "suggestion": "Extract common functionality"
                }
            ]
        }

        result_state = await review_agent._verify_design_principles(sample_state)

        assert result_state.current_step == "principles_complete"
        assert len(result_state.findings) == 1
        assert result_state.findings[0].principle_violated == "DRY"

    @pytest.mark.asyncio
    async def test_generate_review_summary(self, review_agent, sample_state):
        """Test review summary generation."""
        # Add some findings to the state
        sample_state.findings = [
            ReviewFinding(
                category="security",
                severity="critical",
                message="Critical security issue"
            ),
            ReviewFinding(
                category="logic",
                severity="high",
                message="Logic error found"
            )
        ]

        review_agent.llm.ainvoke.return_value = "Review completed with 2 critical issues found."

        result_state = await review_agent._generate_review_summary(sample_state)

        assert result_state.current_step == "complete"
        assert hasattr(result_state, 'review_summary')
        assert hasattr(result_state, 'review_comments')
        assert hasattr(result_state, 'recommendation')
        assert result_state.recommendation == "request_changes"  # Due to critical finding

    @pytest.mark.asyncio
    async def test_review_pull_request_integration(self, review_agent, sample_review_data):
        """Test complete pull request review workflow."""
        # Mock all LLM responses
        responses = [
            {"findings": [{"category": "logic", "severity": "medium", "message": "Logic issue"}]},
            {"findings": [{"category": "security", "severity": "low", "message": "Minor security note"}]},
            {"findings": []},  # No critical bugs
            {"findings": []},  # No naming issues
            {"findings": []},  # No optimization issues
            {"findings": []},  # No principle violations
            "Review completed successfully with minor issues found."
        ]

        review_agent.llm.ainvoke = AsyncMock(side_effect=responses)

        result = await review_agent.review_pull_request(
            review_data=sample_review_data,
            diff_content="test diff",
            file_contents={"test.py": "test content"},
            project_structure={"project_type": "python"}
        )

        assert result["repository"] == "test/repo"
        assert result["pr_number"] == 123
        assert "summary" in result
        assert "recommendation" in result
        assert "comments" in result
        assert result["total_findings"] >= 0

    @pytest.mark.asyncio
    async def test_review_pull_request_error_handling(self, review_agent, sample_review_data):
        """Test error handling in pull request review."""
        # Mock LLM to fail
        review_agent.review_graph.ainvoke = AsyncMock(side_effect=Exception("Workflow failed"))

        result = await review_agent.review_pull_request(
            review_data=sample_review_data,
            diff_content="test diff",
            file_contents={},
            project_structure={}
        )

        assert result["repository"] == "test/repo"
        assert result["pr_number"] == 123
        assert "failed" in result["summary"].lower()
        assert result["error"] is not None


class TestReviewFinding:
    """Tests for ReviewFinding model."""

    def test_review_finding_creation(self):
        """Test creating a ReviewFinding."""
        finding = ReviewFinding(
            category="security",
            severity="high",
            message="Security vulnerability found",
            file_path="auth.py",
            line_number=42,
            suggestion="Add input validation",
            principle_violated="Security First"
        )

        assert finding.category == "security"
        assert finding.severity == "high"
        assert finding.message == "Security vulnerability found"
        assert finding.file_path == "auth.py"
        assert finding.line_number == 42
        assert finding.suggestion == "Add input validation"
        assert finding.principle_violated == "Security First"

    def test_review_finding_minimal(self):
        """Test ReviewFinding with minimal required fields."""
        finding = ReviewFinding(
            category="logic",
            severity="medium",
            message="Logic issue detected"
        )

        assert finding.category == "logic"
        assert finding.severity == "medium"
        assert finding.message == "Logic issue detected"
        assert finding.file_path is None
        assert finding.line_number is None


class TestLogicalReviewState:
    """Tests for LogicalReviewState model."""

    def test_state_creation(self):
        """Test creating LogicalReviewState."""
        review_data = ReviewData(
            repository="test/repo",
            pr_number=123,
            title="Test PR",
            description="Test PR description",
            author="testuser",
            base_branch="main",
            head_branch="feature",
            base_sha="abc123",
            head_sha="def456",
            diff_url="https://github.com/test/repo/pull/123.diff",
            clone_url="https://github.com/test/repo.git"
        )

        state = LogicalReviewState(
            review_data=review_data,
            diff_content="test diff",
            file_contents={"test.py": "content"},
            project_structure={"type": "python"}
        )

        assert state.review_data.repository == "test/repo"
        assert state.review_data.pr_number == 123
        assert state.diff_content == "test diff"
        assert len(state.file_contents) == 1
        assert state.current_step == "start"
        assert len(state.findings) == 0
        assert state.error is None

    def test_state_with_findings(self):
        """Test LogicalReviewState with findings."""
        review_data = ReviewData(
            repository="test/repo",
            pr_number=123,
            title="Test PR",
            description="Test PR description",
            author="testuser",
            base_branch="main",
            head_branch="feature",
            base_sha="abc123",
            head_sha="def456",
            diff_url="https://github.com/test/repo/pull/123.diff",
            clone_url="https://github.com/test/repo.git"
        )

        finding = ReviewFinding(
            category="security",
            severity="high",
            message="Security issue"
        )

        state = LogicalReviewState(
            review_data=review_data,
            diff_content="test diff",
            findings=[finding]
        )

        assert len(state.findings) == 1
        assert state.findings[0].category == "security"
