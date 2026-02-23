# Contributing to ACR System

Thank you for your interest in contributing to the ACR (Automated Code Review) System!

## Development Setup

### Prerequisites

- Python 3.11 or higher
- Git
- pip or uv

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-org/acr-system.git
   cd acr-system
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # or: venv\Scripts\activate  # Windows
   ```

3. **Install dependencies**
   ```bash
   # Install all dependencies including dev tools
   pip install -e ".[all]"
   ```

4. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env and add your API keys
   ```

5. **Install pre-commit hooks**
   ```bash
   pre-commit install
   ```

## Architecture Overview

The project follows **Clean Architecture** and **Hexagonal Architecture** principles:

```
acr_system/
├── domain/              # Business logic and rules (no dependencies)
│   ├── entities/        # Domain entities (PullRequest, DiffHunk, etc.)
│   ├── value_objects/   # Immutable value objects
│   ├── interfaces/      # Ports (abstractions for adapters)
│   └── services/        # Domain services (orchestration)
├── application/         # Use cases and application logic
│   ├── use_cases/       # Use case implementations
│   └── dto/             # Data Transfer Objects
├── infrastructure/      # External adapters (databases, APIs, etc.)
│   ├── vcs/             # GitHub/GitLab adapters
│   ├── llm/             # LLM provider adapters (OpenAI, Anthropic)
│   ├── rag/             # RAG/vector store implementations
│   └── config/          # Configuration loaders
└── presentation/        # User interfaces (API, CLI)
    ├── api/             # FastAPI REST API
    └── cli/             # Click CLI
```

### Key Principles

1. **Dependency Rule**: Dependencies point inward (Infrastructure → Application → Domain)
2. **Interface Segregation**: Small, focused interfaces (ports)
3. **Dependency Inversion**: Depend on abstractions, not concretions
4. **Single Responsibility**: Each module has one reason to change

## Development Workflow

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=acr_system --cov-report=html

# Run specific test file
pytest tests/unit/test_entities.py

# Run with verbose output
pytest -v
```

### Code Quality

```bash
# Format code with Black
black acr_system tests

# Lint with Ruff
ruff check acr_system tests

# Type check with MyPy
mypy acr_system

# Run all checks
pre-commit run --all-files
```

### Running the Application

**CLI:**
```bash
# Review a PR
acr review --pr-url https://github.com/owner/repo/pull/123

# With auto-publish
acr review --pr-url https://github.com/owner/repo/pull/123 --publish
```

**API Server:**
```bash
# Development mode
uvicorn acr_system.presentation.api.main:app --reload

# Production mode
uvicorn acr_system.presentation.api.main:app --host 0.0.0.0 --port 8000
```

## Adding New Features

### Adding a New VCS Provider

1. Create adapter in `infrastructure/vcs/`
2. Implement `VCSRepository` interface from `domain/interfaces/ports.py`
3. Add tests in `tests/unit/infrastructure/vcs/`
4. Update CLI/API to support new provider

Example:
```python
# infrastructure/vcs/bitbucket_adapter.py
from acr_system.domain.interfaces.ports import VCSRepository

class BitbucketAdapter(VCSRepository):
    async def get_pull_request(self, repo: str, pr_number: int):
        # Implementation
        pass
```

### Adding a New LLM Provider

1. Create adapter in `infrastructure/llm/`
2. Implement `LLMProvider` interface
3. Add to provider factory/selector
4. Add tests

### Adding New Rules

Rules are defined in `.acr-config.yml` in each repository. No code changes needed!

## Testing Guidelines

### Unit Tests
- Test domain entities and value objects in isolation
- Mock external dependencies
- Use fixtures from `tests/conftest.py`

```python
def test_create_pull_request():
    pr = PullRequest(
        pr_number=123,
        repository="owner/repo",
        title="Test PR",
        # ...
    )
    assert pr.pr_number == 123
```

### Integration Tests
- Test interactions between layers
- Use real adapters with test doubles
- Test use cases end-to-end

### E2E Tests
- Test full workflow with external systems
- Use test repositories and API keys
- Run sparingly (slow and costly)

## Code Style

### Python Style Guide
- Follow PEP 8
- Use type hints for all functions
- Add docstrings to public functions/classes
- Maximum line length: 100 characters
- Use f-strings for string formatting

### Example
```python
async def process_review(pr_number: int, repo: str) -> ReviewResult:
    """Process a pull request review.
    
    Args:
        pr_number: Pull request number
        repo: Repository in format "owner/repo"
        
    Returns:
        ReviewResult with generated comments
    """
    # Implementation
    pass
```

## Pull Request Process

1. **Fork** the repository
2. **Create branch** from `main`
   ```bash
   git checkout -b feature/my-feature
   ```
3. **Make changes** and commit
   ```bash
   git add .
   git commit -m "feat: add new feature"
   ```
4. **Run tests and linters**
   ```bash
   pytest
   black acr_system tests
   ruff check acr_system tests
   mypy acr_system
   ```
5. **Push** to your fork
   ```bash
   git push origin feature/my-feature
   ```
6. **Create Pull Request** on GitHub
7. **Wait for review** and address feedback

### Commit Message Format

Use [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `test:` Test additions/changes
- `refactor:` Code refactoring
- `chore:` Maintenance tasks

Example: `feat: add GitLab adapter for VCS integration`

## Questions?

- Open an issue on GitHub
- Join our discussions
- Contact maintainers

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
