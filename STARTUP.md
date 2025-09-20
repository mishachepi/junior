# 🚀 Junior Agent - Complete Startup Guide

## ✅ **System Status: READY FOR PRODUCTION**

Your Junior AI Code Review Agent has been fully tested and is ready to review PRs!

## 🔧 **Environment Setup**

### 1. Required Environment Variables

Create your `.env` file:
```bash
cp .env.example .env
```

Add these **required** variables:
```env
# GitHub Integration (REQUIRED)
GITHUB_TOKEN=ghp_your_github_personal_access_token

# AI Provider (REQUIRED - choose one)
OPENAI_API_KEY=sk-your_openai_api_key
# OR
ANTHROPIC_API_KEY=sk-ant-your_anthropic_api_key

# Optional Security
GITHUB_WEBHOOK_SECRET=your_webhook_secret
SECRET_KEY=your_app_secret_key
```

### 2. GitHub Token Setup

Create a GitHub Personal Access Token with these permissions:
- `repo` - Full repository access
- `pull_requests:write` - Create reviews and comments  
- `metadata:read` - Read repository metadata

## 🎯 **Start the Agent**

### Option 1: Quick Start Script
```bash
./scripts/start.sh
```

### Option 2: Manual Start
```bash
# Test everything works
uv run python scripts/quick_test.py

# Start the webhook server
uv run junior webhook-server --port 8000
```

### Option 3: Direct FastAPI
```bash
uv run uvicorn junior.app:app --host 0.0.0.0 --port 8000
```

## 🔌 **GitHub Webhook Configuration**

1. Go to your repository → **Settings** → **Webhooks** → **Add webhook**

2. Configure webhook:
   ```
   Payload URL: https://your-server.com/webhook/github
   Content Type: application/json
   Secret: your_webhook_secret (optional but recommended)
   Events: ✅ Pull requests
   Active: ✅ Active
   ```

3. Test webhook:
   - Create a test PR
   - Check webhook deliveries in GitHub
   - Check your server logs

## 📊 **Available Endpoints**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Health check - always works |
| `/ready` | GET | Readiness check - requires GitHub token |
| `/webhook/github` | POST | Main webhook endpoint for PR events |
| `/review` | POST | Manual review endpoint (debug mode only) |

## 🧪 **Testing Commands**

```bash
# Test all imports and basic functionality
uv run python scripts/quick_test.py

# Test complete end-to-end flow (with mocks)
uv run python scripts/test_complete_flow.py

# Test webhook with realistic data (requires running server)
uv run python scripts/test_webhook_simple.py

# Test health endpoint
curl http://localhost:8000/health

# Test readiness (requires GITHUB_TOKEN)
curl http://localhost:8000/ready

# Check configuration and API connectivity
uv run junior config-check

# View all available CLI commands
uv run junior --help
```

## 🔍 **Execution Flow Verified**

✅ **1. Webhook Reception** (`/webhook/github`)
- Receives GitHub PR events
- Validates payload structure
- Verifies webhook signature (if configured)
- Filters for relevant events (opened, synchronize, ready_for_review)

✅ **2. PR Data Extraction** (`WebhookProcessor`)
- Extracts comprehensive PR metadata
- Parses linked issues (`fixes #123`)
- Collects commit history and file changes
- Gathers repository context

✅ **3. Repository Analysis** (`RepositoryAnalyzer`)
- Clones repository to temporary directory
- Analyzes project structure (Python, Node.js, etc.)
- Prioritizes files: changed → config → context → entry points
- Extracts relevant file contents with smart limits

✅ **4. AI Review Pipeline** (`LogicalReviewAgent`)
- **Logic Analysis**: Business logic, conditional flows, edge cases
- **Security Review**: Authentication logic, business vulnerabilities
- **Critical Bug Detection**: Memory safety, race conditions, zero-day potential
- **Naming Review**: Semantic clarity, domain appropriateness
- **Optimization Analysis**: Performance bottlenecks, algorithmic improvements
- **Design Principles**: DRY, KISS, SOLID adherence

✅ **5. GitHub Integration** (`GitHubClient`)
- Formats review summary with severity breakdown
- Creates inline comments (max 20 most critical)
- Submits review with appropriate status (approve/request_changes/comment)

## 📝 **Sample Review Output**

Junior will post reviews like this:

```markdown
## 🤖 Junior Code Review

This PR introduces new authentication logic with a few concerns around error handling and security.

📊 **Findings Summary**: 3 total • 🔴 1 critical • 🟡 2 medium

---
*Reviewed by Junior AI Agent - Focusing on logic, security, and code quality*
```

Plus inline comments on specific lines with suggestions.

## 🚨 **Review Focus Areas**

Junior specializes in **logical analysis**, not linting:

**✅ What Junior Reviews:**
- Business logic correctness
- Security vulnerabilities (logical)
- Critical bugs and race conditions
- Naming semantics and clarity
- Performance bottlenecks
- Design principle violations

**❌ What Junior Ignores:**
- Code formatting (use Prettier/Black)
- Syntax errors (use your IDE)
- Style guide violations (use ESLint/Ruff)
- Dependency vulnerabilities (use Dependabot)

## 🐳 **Docker Deployment**

```bash
# Build and run
docker build -t junior .
docker run -p 8000:8000 --env-file .env junior

# Or use docker-compose
docker-compose up -d
```
