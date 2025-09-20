# Junior - AI Code Review Agent

An intelligent, webhook-based AI agent that provides comprehensive code reviews for GitHub pull requests, focusing on logic, security, critical bugs, and code quality.

## 🚀 Quick Start

1. **Clone and setup:**
   ```bash
   git clone <repository-url>
   cd junior
   uv sync --all-extras
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

3. **Test the setup:**
   ```bash
   uv run python scripts/quick_test.py
   ```

4. **Start the webhook server:**
   ```bash
   ./scripts/start.sh
   # OR
   uv run junior webhook-server --port 8000
   ```

## 🔧 Configuration

Required environment variables:
- `GITHUB_TOKEN` - GitHub Personal Access Token with repo permissions
- Either `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` - AI provider API key

Optional:
- `GITHUB_WEBHOOK_SECRET` - GitHub webhook secret for security
- `SECRET_KEY` - Application secret key

## 📋 How It Works

### The Review Flow

1. **GitHub PR Event** → Webhook receives PR opened/updated/ready-for-review
2. **Data Extraction** → Comprehensive PR information extraction including:
   - PR metadata (title, description, author, branches)
   - Commit history and linked issues  
   - File changes and diff content
   - Repository context and dependencies

3. **MCP Repository Analysis** → Smart analysis with:
   - Temporary repository cloning
   - Project structure detection (Python, Node.js, etc.)
   - Priority-based file content extraction
   - Framework and dependency analysis

4. **AI Review Pipeline** → Specialized review focusing on:
   - **Logic Analysis** - Business logic, conditional flows, edge cases
   - **Security Review** - Authentication logic, business logic vulnerabilities
   - **Critical Bug Detection** - Memory safety, race conditions, zero-day potential
   - **Naming Review** - Semantic clarity, domain appropriateness  
   - **Optimization** - Algorithmic improvements, performance bottlenecks
   - **Design Principles** - DRY, KISS, SOLID adherence

5. **GitHub Integration** → Structured review submission:
   - Review summary with severity breakdown
   - Inline comments (limited to 20 most critical)
   - Approve/Request Changes/Comment status

### What Makes Junior Different

- **Logic-Focused**: Unlike linters, Junior analyzes business logic and architectural decisions
- **Security-Aware**: Identifies logical security vulnerabilities, not just code patterns  
- **Context-Rich**: Uses repository structure and project dependencies for informed reviews
- **Structured Output**: Consistent, actionable feedback with severity levels and suggestions

## 🔌 GitHub Integration

### Webhook Setup

1. Go to your repository → Settings → Webhooks → Add webhook
2. Set Payload URL to: `https://your-server.com/webhook/github`
3. Content type: `application/json`
4. Select: "Pull requests" events
5. Add webhook secret (optional but recommended)

### Required GitHub Token Permissions

- `repo` - Repository access
- `pull_requests:write` - Create reviews and comments

## 🧪 Testing

Run the comprehensive test suite:
```bash
uv run python scripts/quick_test.py
```

Check configuration:
```bash
uv run junior config-check
```

Start webhook server:
```bash
uv run junior webhook-server
```

## 📁 Project Structure

```
junior/
├── src/junior/
│   ├── api.py              # FastAPI webhook service  
│   ├── webhook.py          # GitHub webhook processing
│   ├── review_agent.py     # Specialized AI review pipeline
│   ├── mcp_tools.py        # Repository analysis tools
│   ├── github_client.py    # GitHub API integration
│   ├── models.py           # Data models and schemas
│   ├── config.py          # Configuration management
│   └── cli.py             # CLI (config-check, webhook-server)
├── tests/                 # Test suite
├── scripts/              # Utility scripts  
├── helm/                # Kubernetes deployment
└── docs/                # Documentation
```

## 🚨 Review Categories

Junior focuses on high-impact issues:

- **Logic Issues** - Incorrect business logic, missing edge cases
- **Security** - Authentication flaws, business logic vulnerabilities  
- **Critical Bugs** - Memory safety, race conditions, data corruption
- **Naming** - Semantic clarity, domain appropriateness
- **Optimization** - Performance bottlenecks, algorithmic improvements
- **Principles** - DRY, KISS, SOLID violations

## 🛠️ Development

### Running Tests
```bash
uv run pytest
uv run pytest --cov=src/junior --cov-report=xml
```

### Code Quality
```bash
uv run ruff check .
uv run ruff format .
uv run mypy src/
```

### Development Server
```bash
uv run junior webhook-server --reload --debug
```

## 🐳 Docker

### Build and Run
```bash
# Build image
docker build -t junior .

# Run with docker-compose
docker-compose up -d
```

## ☸️ Kubernetes Deployment

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

## ⚙️ Advanced Configuration

### Review Settings
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

## 🏗️ Architecture

Junior uses a modern, webhook-driven architecture:

- **FastAPI** - Webhook endpoints and API services
- **LangChain + LangGraph** - Structured AI workflows  
- **MCP Tools** - Repository analysis and understanding
- **Pydantic** - Data validation and settings
- **GitPython** - Git operations and repository analysis

### Review Pipeline Architecture

```
GitHub PR Event → Webhook Validation → Repository Cloning → 
File Analysis → AI Review Pipeline → GitHub API Response
```

Each step is optimized for accuracy and performance, with comprehensive error handling and logging.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run the test suite
6. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 📞 Support

- 🐛 [Issue Tracker](https://github.com/yourusername/junior/issues)
- 💬 [Discussions](https://github.com/yourusername/junior/discussions)
- 📖 [Documentation](https://github.com/yourusername/junior/wiki)