.PHONY: help install test test-unit test-integration lint format typecheck clean run webhook docker-build docker-up docker-down coverage pre-commit review-local

# Default target
help:
	@echo "Available targets:"
	@echo "  install          - Install dependencies with uv"
	@echo "  test             - Run all tests"
	@echo "  test-unit        - Run unit tests only"
	@echo "  test-integration - Run integration tests only"
	@echo "  lint             - Run linting checks"
	@echo "  format           - Format code with ruff"
	@echo "  typecheck        - Run type checking with mypy"
	@echo "  clean            - Clean cache and build files"
	@echo "  run              - Start webhook server"
	@echo "  webhook          - Start webhook server (alias)"
	@echo "  docker-build     - Build Docker image"
	@echo "  docker-up        - Start services with docker-compose"
	@echo "  docker-down      - Stop docker-compose services"
	@echo "  coverage         - Run tests with coverage report"
	@echo "  pre-commit       - Run all pre-commit checks"
	@echo "  review-local     - Run review on local changes"

# Development setup
install:
	uv sync --all-extras
	@echo "Don't forget to copy .env.example to .env and configure it!"

# Testing
test:
	python3 -m pytest tests/ --ignore=tests/test_agent.py -v

test-unit:
	python3 -m pytest tests/ --ignore=tests/test_agent.py -m "not integration" -v

test-integration:
	python3 -m pytest tests/test_integration.py -m integration -v

# Code quality
lint:
	ruff check .

format:
	ruff format .

typecheck:
	python3 -m mypy src/

# Combined quality check
quality: lint typecheck

# Pre-commit hooks
pre-commit:
	python3 -m pre_commit run --all-files

# Coverage
coverage:
	python3 -m pytest --cov=src/junior --cov-report=xml --cov-report=term-missing --ignore=tests/test_agent.py

# Clean
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name ".coverage" -delete
	find . -type f -name "coverage.xml" -delete

# Running the application
run: webhook

webhook:
	python3 -m junior.api

# Docker operations
docker-build:
	docker build -t junior .

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

# CLI commands
review-local:
	junior review-local --base main

config-check:
	junior config-check

# Quick commands for common workflows
quick-test: format lint test-unit

ci: lint typecheck test coverage

# Development server with auto-reload
dev:
	uvicorn junior.api:app --reload --port 8000

# Setup environment from template
setup-env:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo ".env file created from template. Please edit it with your API keys."; \
	else \
		echo ".env file already exists"; \
	fi