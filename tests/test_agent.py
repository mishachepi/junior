"""Tests for the code review agent."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from junior.agent import CodeReviewAgent, ReviewState
from junior.models import (
    CodeReviewRequest,
    FileChange,
    FileStatus,
    ReviewCategory,
    Severity,
)


class TestCodeReviewAgent:
    """Tests for CodeReviewAgent."""

    def test_agent_initialization(self, mock_settings, monkeypatch):
        """Test agent initialization."""
        monkeypatch.setattr("junior.config.settings", mock_settings)
        
        with patch("junior.agent.ChatOpenAI") as mock_chat:
            agent = CodeReviewAgent()
            assert agent is not None
            mock_chat.assert_called_once()

    def test_agent_initialization_without_api_key(self, monkeypatch):
        """Test agent initialization fails without API key."""
        from junior.config import Settings
        
        bad_settings = Settings(
            github_token="test-token",
            secret_key="test-secret",
        )
        monkeypatch.setattr("junior.config.settings", bad_settings)
        
        with pytest.raises(ValueError, match="No AI API key provided"):
            CodeReviewAgent()

    @pytest.mark.asyncio
    async def test_analyze_files(self, code_review_agent, sample_review_request):
        """Test file analysis step."""
        state = ReviewState(request=sample_review_request)
        
        result_state = await code_review_agent._analyze_files(state)
        
        assert len(result_state.file_changes) == 1
        assert result_state.file_changes[0].filename == "test.py"

    @pytest.mark.asyncio
    async def test_security_review(self, code_review_agent, sample_review_request):
        """Test security review step."""
        state = ReviewState(
            request=sample_review_request,
            file_changes=sample_review_request.files
        )
        
        # Mock the LLM response
        code_review_agent.llm.ainvoke = AsyncMock(
            return_value="Found potential SQL injection on line 42"
        )
        
        result_state = await code_review_agent._security_review(state)
        
        assert len(result_state.security_issues) > 0
        assert len(result_state.comments) > 0

    @pytest.mark.asyncio
    async def test_security_review_disabled(self, code_review_agent, sample_review_request, monkeypatch):
        """Test security review when disabled."""
        from junior.config import Settings
        
        settings_with_disabled_security = Settings(
            openai_api_key="test-key",
            github_token="test-token",
            secret_key="test-secret",
            enable_security_checks=False,
        )
        monkeypatch.setattr("junior.config.settings", settings_with_disabled_security)
        
        state = ReviewState(
            request=sample_review_request,
            file_changes=sample_review_request.files
        )
        
        result_state = await code_review_agent._security_review(state)
        
        assert len(result_state.security_issues) == 0

    @pytest.mark.asyncio
    async def test_performance_review(self, code_review_agent, sample_review_request):
        """Test performance review step."""
        state = ReviewState(
            request=sample_review_request,
            file_changes=sample_review_request.files
        )
        
        # Mock the LLM response
        code_review_agent.llm.ainvoke = AsyncMock(
            return_value="Inefficient loop detected"
        )
        
        result_state = await code_review_agent._performance_review(state)
        
        assert len(result_state.performance_issues) > 0

    @pytest.mark.asyncio
    async def test_style_review(self, code_review_agent, sample_review_request):
        """Test style review step."""
        state = ReviewState(
            request=sample_review_request,
            file_changes=sample_review_request.files
        )
        
        # Mock the LLM response
        code_review_agent.llm.ainvoke = AsyncMock(
            return_value="Variable naming is inconsistent"
        )
        
        result_state = await code_review_agent._style_review(state)
        
        assert len(result_state.style_issues) > 0

    @pytest.mark.asyncio
    async def test_complexity_review(self, code_review_agent, sample_review_request):
        """Test complexity review step."""
        state = ReviewState(
            request=sample_review_request,
            file_changes=sample_review_request.files
        )
        
        # Mock the LLM response
        code_review_agent.llm.ainvoke = AsyncMock(
            return_value="Function is too complex, consider refactoring"
        )
        
        result_state = await code_review_agent._complexity_review(state)
        
        assert len(result_state.complexity_issues) > 0

    @pytest.mark.asyncio
    async def test_generate_summary(self, code_review_agent, sample_review_request):
        """Test summary generation step."""
        from junior.models import ReviewComment
        
        state = ReviewState(
            request=sample_review_request,
            file_changes=sample_review_request.files,
            comments=[
                ReviewComment(category=ReviewCategory.SECURITY, message="Security issue"),
                ReviewComment(category=ReviewCategory.PERFORMANCE, message="Performance issue"),
            ],
            security_issues=[
                ReviewComment(category=ReviewCategory.SECURITY, message="Security issue")
            ],
            performance_issues=[
                ReviewComment(category=ReviewCategory.PERFORMANCE, message="Performance issue")
            ],
        )
        
        # Mock the LLM response
        code_review_agent.llm.ainvoke = AsyncMock(
            return_value="Overall assessment: Please address the security and performance issues before merging."
        )
        
        result_state = await code_review_agent._generate_summary(state)
        
        assert result_state.summary is not None
        assert "security and performance issues" in result_state.summary

    @pytest.mark.asyncio
    async def test_review_code_integration(self, code_review_agent, sample_review_request):
        """Test complete code review workflow."""
        # Mock all LLM responses
        responses = [
            "Found security issue",
            "Found performance issue", 
            "Found style issue",
            "Found complexity issue",
            "Review completed successfully"
        ]
        code_review_agent.llm.ainvoke = AsyncMock(side_effect=responses)
        
        result = await code_review_agent.review_code(sample_review_request)
        
        assert result.pr_number == sample_review_request.pr_number
        assert result.repository == sample_review_request.repository
        assert result.summary is not None
        assert len(result.comments) > 0

    @pytest.mark.asyncio
    async def test_review_code_error_handling(self, code_review_agent, sample_review_request):
        """Test error handling in code review."""
        # Mock LLM to raise an exception
        code_review_agent.llm.ainvoke = AsyncMock(side_effect=Exception("API Error"))
        
        result = await code_review_agent.review_code(sample_review_request)
        
        assert result.pr_number == sample_review_request.pr_number
        assert "failed" in result.summary.lower()

    def test_format_changes(self, code_review_agent, sample_file_change):
        """Test formatting file changes for AI review."""
        formatted = code_review_agent._format_changes([sample_file_change])
        
        assert "File: test.py" in formatted
        assert "Status: modified" in formatted
        assert sample_file_change.diff in formatted

    def test_parse_review_response(self, code_review_agent):
        """Test parsing AI response into review comments."""
        response = """Found potential security issue
Another issue here
Third issue found"""
        
        comments = code_review_agent._parse_review_response(response, "security")
        
        assert len(comments) == 3
        assert all(comment.category == "security" for comment in comments)
        assert all(comment.severity == Severity.MEDIUM for comment in comments)

    def test_parse_review_response_empty(self, code_review_agent):
        """Test parsing empty AI response."""
        comments = code_review_agent._parse_review_response("", "security")
        assert len(comments) == 0
        
        comments = code_review_agent._parse_review_response(None, "security")
        assert len(comments) == 0


class TestReviewState:
    """Tests for ReviewState model."""

    def test_review_state_creation(self, sample_review_request):
        """Test creating ReviewState."""
        state = ReviewState(request=sample_review_request)
        
        assert state.request == sample_review_request
        assert state.file_changes == []
        assert state.comments == []
        assert state.summary is None
        assert state.error is None

    def test_review_state_with_data(self, sample_review_request, sample_file_change):
        """Test ReviewState with data."""
        from junior.models import ReviewComment
        
        comment = ReviewComment(category=ReviewCategory.SECURITY, message="Test issue")
        
        state = ReviewState(
            request=sample_review_request,
            file_changes=[sample_file_change],
            comments=[comment],
            summary="Test summary",
        )
        
        assert len(state.file_changes) == 1
        assert len(state.comments) == 1
        assert state.summary == "Test summary"