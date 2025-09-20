#!/bin/bash
# Startup script for Junior webhook service

set -e

echo "🤖 Starting Junior AI Code Review Agent..."

# Check if .env file exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Copying from .env.example"
    cp .env.example .env
    echo "📝 Please edit .env with your API keys and configuration"
    exit 1
fi

# Source environment variables
source .env

# Check required environment variables
required_vars=("GITHUB_TOKEN")
missing_vars=()

for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        missing_vars+=("$var")
    fi
done

if [ ${#missing_vars[@]} -ne 0 ]; then
    echo "❌ Missing required environment variables:"
    printf '   %s\n' "${missing_vars[@]}"
    echo "Please set these in your .env file"
    exit 1
fi

# Check if at least one AI provider is configured
if [ -z "$OPENAI_API_KEY" ] && [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "❌ No AI provider configured. Please set either OPENAI_API_KEY or ANTHROPIC_API_KEY in .env"
    exit 1
fi

# Install dependencies if needed
if [ ! -d ".venv" ]; then
    echo "📦 Installing dependencies with uv..."
    uv sync
fi

# Create necessary directories
mkdir -p logs temp

# Start the service
echo "🚀 Starting webhook server on ${API_HOST:-0.0.0.0}:${API_PORT:-8000}"
echo "📝 Logs will be written to logs/ directory"
echo "🔧 Temporary files will be stored in temp/ directory"
echo ""
echo "Webhook endpoint: http://${API_HOST:-0.0.0.0}:${API_PORT:-8000}/webhook/github"
echo "Health check: http://${API_HOST:-0.0.0.0}:${API_PORT:-8000}/health"
echo ""

# Run the webhook server
uv run python -m junior.app