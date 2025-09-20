# Junior - AI Code Review Agent

An intelligent AI agent built with LangChain and LangGraph for automated code review of pull requests. Junior provides comprehensive analysis including security, performance, style, and complexity checks.

## Features

- 🔍 **Comprehensive Code Analysis**
  - Security vulnerability detection
  - Performance bottleneck identification
  - Code style and formatting checks
  - Complexity analysis and refactoring suggestions

- 🤖 **AI-Powered Reviews**
  - Support for OpenAI and Anthropic models
  - Structured workflow using LangGraph
  - Context-aware analysis with LangChain

- 🔧 **GitHub Integration**
  - Automatic PR review triggering
  - Inline code comments
  - Review summaries and recommendations

- 📊 **Flexible Configuration**
  - Customizable review criteria
  - Configurable AI models and parameters
  - Environment-based settings

## Quick Start

### Prerequisites

- Python 3.11+
- uv (recommended) or pip
- GitHub token with repo access
- OpenAI or Anthropic API key

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/junior.git
cd junior

# Install with uv (recommended)
uv sync

# Or with pip
pip install -e .
```

### Configuration

1. Copy the environment template:
```bash
cp .env.example .env
```

2. Edit `.env` with your API keys:
```env
OPENAI_API_KEY=your_openai_api_key
GITHUB_TOKEN=your_github_token
SECRET_KEY=your_secret_key
```

### Usage

#### Review a Pull Request
```bash
junior review-pr owner/repo 123
```

#### Review Local Changes
```bash
junior review-local --base main
```

#### Check Configuration
```bash
junior config-check
```

## Development

### Setup Development Environment

```bash
# Install with development dependencies
uv sync --all-extras

# Install pre-commit hooks
uv run pre-commit install

# Run tests
uv run pytest

# Run linting
uv run ruff check .
uv run ruff format .

# Type checking
uv run mypy src/
```

### Project Structure

```
junior/
├── src/junior/           # Main application code
│   ├── __init__.py
│   ├── agent.py         # Core AI agent logic
│   ├── config.py        # Configuration management
│   ├── models.py        # Data models
│   ├── cli.py           # Command line interface
│   ├── github_client.py # GitHub API client
│   └── git_client.py    # Local Git operations
├── tests/               # Test files
├── helm/                # Kubernetes deployment
├── .github/workflows/   # CI/CD pipelines
├── pyproject.toml       # Project configuration
└── README.md
```

## Docker

### Build and Run

```bash
# Build image
docker build -t junior .

# Run with docker-compose
docker-compose up -d
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | - |
| `ANTHROPIC_API_KEY` | Anthropic API key | - |
| `GITHUB_TOKEN` | GitHub token | - |
| `SECRET_KEY` | Application secret | - |
| `LOG_LEVEL` | Logging level | `INFO` |
| `DEBUG` | Debug mode | `false` |

## Kubernetes Deployment

Deploy to Kubernetes using Helm:

```bash
# Install dependencies
helm dependency update helm/junior

# Deploy
helm install junior helm/junior \
  --set secrets.openaiApiKey="your-key" \
  --set secrets.githubToken="your-token" \
  --set secrets.secretKey="your-secret"
```

## Configuration

### Review Settings

Configure review behavior in your `.env` file:

```env
# Review toggles
ENABLE_SECURITY_CHECKS=true
ENABLE_PERFORMANCE_CHECKS=true
ENABLE_STYLE_CHECKS=true
ENABLE_COMPLEXITY_CHECKS=true

# Review limits
MAX_FILE_SIZE=100000
MAX_FILES_PER_PR=50
REVIEW_TIMEOUT=300
```

### AI Model Settings

```env
# Model configuration
DEFAULT_MODEL=gpt-4o
TEMPERATURE=0.1
MAX_TOKENS=4000
```

## Architecture

Junior is built using modern Python patterns and AI frameworks:

- **LangChain**: For LLM integration and prompt management
- **LangGraph**: For structured AI workflows
- **Pydantic**: For data validation and settings
- **uv**: For fast dependency management
- **Kubernetes**: For scalable deployment

The review process follows a structured workflow:

1. **File Analysis**: Parse and categorize changed files
2. **Security Review**: Check for vulnerabilities
3. **Performance Review**: Identify bottlenecks
4. **Style Review**: Enforce coding standards
5. **Complexity Review**: Suggest refactoring
6. **Summary Generation**: Create actionable feedback

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run the test suite
6. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

- 📖 [Documentation](https://github.com/yourusername/junior/wiki)
- 🐛 [Issue Tracker](https://github.com/yourusername/junior/issues)
- 💬 [Discussions](https://github.com/yourusername/junior/discussions)
