# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Development Commands

### Environment Setup
```bash
# Install dependencies with uv (required)
uv sync --all-extras

# Copy environment template and configure
cp .env.example .env
# Edit .env with required API keys: GITHUB_TOKEN, SECRET_KEY, and either OPENAI_API_KEY or ANTHROPIC_API_KEY
```

### Testing
```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_api.py

# Run with coverage
uv run pytest --cov=src/junior --cov-report=xml --cov-report=term-missing

# Run specific test markers
uv run pytest -m unit
uv run pytest -m integration
```

### Code Quality
```bash
# Linting and formatting
uv run ruff check .
uv run ruff format .

# Type checking
uv run mypy src/

# Pre-commit hooks (run all checks)
uv run pre-commit run --all-files
```

### Running the Application
```bash
# Start webhook server (main service)
junior webhook-server --port 8000
# OR
python -m junior.api

# CLI commands for manual testing
junior review-pr owner/repo 123
junior review-local --base main
junior config-check

# Quick start script
./scripts/start.sh
```

### Docker
```bash
# Build and run with compose
docker-compose up -d

# Build standalone image
docker build -t junior .
```

## Architecture Overview

Junior is a webhook-based AI code review agent with two distinct processing paths:

### Core Components Architecture

**Service Layer:**
- `api.py` - FastAPI webhook service that receives GitHub PR events and orchestrates reviews
- `webhook.py` - GitHub webhook processing and validation logic
- `cli.py` - Command-line interface for manual operations

**AI Review Pipeline:**
- `review_agent.py` - Specialized AI agent implementing logical review workflow via LangGraph
- `agent.py` - Original general-purpose review agent (legacy, kept for CLI operations)
- Both agents use structured LangGraph workflows but focus on different review criteria

**Repository Analysis:**
- `mcp_tools.py` - MCP (Model Context Protocol) integration for deep repository analysis
- `repository_analyzer.py` - Orchestrates repo structure analysis and context enrichment
- `github_client.py` / `git_client.py` - GitHub API and local Git operations

**Data Layer:**
- `models.py` - Pydantic models for all data structures with extensive enum definitions
- `config.py` - Centralized configuration via Pydantic Settings with environment variable mapping

### Review Focus Areas

The system specifically targets logical and architectural issues, NOT linting:

**Primary Review Categories** (in `models.ReviewCategory`):
- `LOGIC` - Business logic, conditional flows, edge cases
- `SECURITY` - Authentication flows, authorization logic, business logic vulnerabilities
- `CRITICAL_BUG` - Memory safety, race conditions, zero-day potential
- `NAMING` - Semantic clarity, domain appropriateness (not style guide compliance)
- `OPTIMIZATION` - Algorithmic efficiency, performance bottlenecks
- `DRY_VIOLATION` / `KISS_VIOLATION` - Design principle adherence

### Webhook Processing Flow

1. **GitHub Event Reception** (`api.py` `/webhook/github`)
   - Signature verification via HMAC
   - Event filtering (only PR opens/updates/ready-for-review)
   - Background task queuing

2. **Repository Analysis** (`mcp_tools.py` + `repository_analyzer.py`)
   - Temporary repo cloning
   - Project structure detection (Python/Node.js/Java/etc.)
   - Risk factor assessment (security files, config changes, etc.)
   - File content extraction with smart filtering

3. **AI Review Pipeline** (`review_agent.py` LangGraph workflow)
   - Logic analysis → Security review → Critical bug detection → Naming review → Optimization → Design principles
   - Each step uses specialized prompts and JSON-structured responses
   - Findings aggregated with severity levels

4. **GitHub Integration** (back to `api.py`)
   - Review summary formatting
   - Inline comment posting (limited to 20 per PR)
   - Review submission with approve/request-changes/comment status

### Configuration Strategy

All configuration via environment variables through `config.py`:
- AI provider keys (OpenAI/Anthropic) - at least one required
- GitHub integration (token + optional webhook secret)
- Review behavior toggles (enable/disable specific check types)
- Processing limits (max files per PR, timeouts)

### Testing Strategy

Test structure mirrors src/ with comprehensive mocking:
- `conftest.py` provides fixtures for common objects (mock clients, sample data)
- Heavy use of `pytest-mock` for async operations and external API calls
- Integration tests marked with `@pytest.mark.integration`
- Test data uses realistic GitHub webhook payloads and git diffs

### MCP Integration Pattern

The `mcp_tools.py` implements repository analysis without external MCP servers:
- Direct git operations via GitPython
- File system analysis with smart filtering by extension/size
- Project type detection via configuration files (package.json, pyproject.toml, etc.)
- Throttled file reading (10 ops/second) to prevent resource exhaustion

Key architectural principle: The system maintains separation between the general-purpose review agent (for CLI use) and the specialized logical review agent (for webhook automation), allowing different review criteria and workflows while sharing common infrastructure.


### Additional
- Ignore "helm" folder
