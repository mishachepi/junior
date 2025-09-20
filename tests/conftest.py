"""Pytest configuration and fixtures."""

import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_openai import ChatOpenAI

from junior.agent import LogicalReviewAgent
from junior.config import Settings
from junior.services import GitHubClient
from junior.models import CodeReviewRequest, FileChange, FileStatus


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    return Settings(
        openai_api_key="test-key",
        github_token="test-token",
        secret_key="test-secret",
        debug=True,
    )


@pytest.fixture
def sample_file_change():
    """Sample file change for testing."""
    return FileChange(
        filename="test.py",
        status=FileStatus.MODIFIED,
        additions=10,
        deletions=5,
        diff="""@@ -1,5 +1,10 @@
 def hello():
-    print("hello")
+    print("hello world")
+    return "hello"
""",
        content="""def hello():
    print("hello world")
    return "hello"
""",
    )


@pytest.fixture
def sample_review_request(sample_file_change):
    """Sample code review request for testing."""
    return CodeReviewRequest(
        repository="test/repo",
        pr_number=123,
        title="Test PR",
        description="A test pull request",
        author="testuser",
        base_branch="main",
        head_branch="feature/test",
        files=[sample_file_change],
    )


@pytest.fixture
def mock_github_client():
    """Mock GitHub client."""
    client = MagicMock(spec=GitHubClient)
    client.get_authenticated_user = AsyncMock(return_value={
        "login": "testuser",
        "name": "Test User",
        "email": "test@example.com",
        "id": 12345,
    })
    client.get_pull_request = AsyncMock(return_value={
        "number": 123,
        "title": "Test PR",
        "body": "Test description",
        "state": "open",
        "user": {"login": "testuser", "id": 12345},
        "base": {"ref": "main", "sha": "abc123"},
        "head": {"ref": "feature/test", "sha": "def456"},
    })
    return client


@pytest.fixture
def mock_llm():
    """Mock LLM for testing."""
    llm = MagicMock(spec=ChatOpenAI)
    llm.ainvoke = AsyncMock(return_value="Mock AI response")
    return llm


@pytest.fixture
def code_review_agent(mock_settings, monkeypatch):
    """Code review agent with mocked dependencies."""
    monkeypatch.setattr("junior.config.settings", mock_settings)
    
    agent = LogicalReviewAgent()
    agent.llm = MagicMock()
    agent.llm.ainvoke = AsyncMock(return_value="Mock review response")
    
    return agent


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Set up test environment variables."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("DEBUG", "true")