#!/bin/bash
# Development startup script for Junior API

echo "🔧 Junior Development Server"
echo "=========================="

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Creating from template..."
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "✅ Created .env from .env.example"
        echo "📝 Please edit .env with your API keys"
    else
        echo "❌ No .env.example found"
        exit 1
    fi
fi

# Set debug mode
export DEBUG=true
export PYTHONPATH="$(pwd)/src"

echo "🚀 Starting Junior API in debug mode with auto-reload..."
echo "📚 API docs will be available at: http://127.0.0.1:8000/docs"
echo "🔍 Health check: http://127.0.0.1:8000/health"
echo ""

# Start with uv
uv run uvicorn junior.api:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    --log-level debug