.PHONY: help install install-dev test test-cov lint format type-check clean run-api run-cli

help:  ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Install project dependencies
	pip install -e .

install-dev:  ## Install all dependencies including dev tools
	pip install -e ".[all]"
	pre-commit install

test:  ## Run tests
	pytest

test-cov:  ## Run tests with coverage report
	pytest --cov=acr_system --cov-report=term-missing --cov-report=html

test-unit:  ## Run only unit tests
	pytest tests/unit

test-integration:  ## Run only integration tests
	pytest tests/integration

lint:  ## Run linter (ruff)
	ruff check acr_system tests

lint-fix:  ## Run linter and auto-fix issues
	ruff check --fix acr_system tests

format:  ## Format code with black
	black acr_system tests

format-check:  ## Check code formatting without changes
	black --check acr_system tests

type-check:  ## Run type checker (mypy)
	mypy acr_system

quality:  ## Run all quality checks (lint, format-check, type-check)
	@echo "Running format check..."
	@make format-check
	@echo "\nRunning linter..."
	@make lint
	@echo "\nRunning type checker..."
	@make type-check
	@echo "\n✓ All quality checks passed!"

pre-commit:  ## Run pre-commit hooks on all files
	pre-commit run --all-files

clean:  ## Clean up generated files
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache/
	rm -rf .ruff_cache/
	rm -rf .mypy_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

run-api:  ## Run FastAPI development server
	uvicorn acr_system.presentation.api.main:app --reload --host 0.0.0.0 --port 8000

run-cli-help:  ## Show CLI help
	acr --help

review-example:  ## Example: Review a PR (set PR_URL environment variable)
	acr review --pr-url $(PR_URL)

dev:  ## Setup development environment
	@echo "Setting up development environment..."
	@make install-dev
	@cp -n .env.example .env || true
	@echo "\n✓ Development environment ready!"
	@echo "Remember to configure .env with your API keys"

ci:  ## Run CI checks (quality + tests)
	@echo "Running CI checks..."
	@make quality
	@make test-cov
	@echo "\n✓ All CI checks passed!"
