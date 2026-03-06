# ACR System - Automated Code Review

System automatycznej recenzji kodu wykorzystujący LLM (GPT-4, Claude) i RAG (Retrieval-Augmented Generation).

## Architektura

System zbudowany zgodnie z zasadami **Clean Architecture** i **Hexagonal Architecture (Ports & Adapters)**:

- **Domain Layer**: Logika biznesowa i reguły domenowe
- **Application Layer**: Use cases i orkiestracja
- **Infrastructure Layer**: Adaptery do systemów zewnętrznych (GitHub, GitLab, OpenAI, etc.)
- **Presentation Layer**: API (FastAPI) i CLI

## Wymagania

- Python 3.11+
- pip lub uv

## Instalacja

```bash
# Tworzenie środowiska wirtualnego
python -m venv venv
source venv/bin/activate  # Linux/Mac
# lub: venv\Scripts\activate  # Windows

# Instalacja podstawowych zależności
pip install -e .

# Instalacja wszystkich zależności (dev + llm + rag + ast)
pip install -e ".[all]"
```

## Konfiguracja

### 1. GitHub App Authentication

System używa GitHub App do autoryzacji. Postępuj zgodnie z [instrukcją konfiguracji](acr_system/infrastructure/auth/README.md):

1. Utwórz GitHub App w ustawieniach organizacji/konta
2. Wygeneruj i pobierz klucz prywatny (.pem)
3. Zainstaluj aplikację w swoich repozytoriach
4. Skonfiguruj zmienne środowiskowe:

```bash
# .env
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY_PATH=./github-app-private-key.pem
GITHUB_APP_INSTALLATION_ID=12345678  # Optional, auto-detect
```

### 2. OpenAI API

```bash
# .env
OPENAI_API_KEY=sk-...
DEFAULT_LLM_MODEL=gpt-4o
```

### 3. Konfiguracja projektu

Skopiuj `.env.example` do `.env` i uzupełnij wartości.

Utwórz konfigurację `.acr-config.yml` w swoim repozytorium:
```yaml
review:
  enabled: true
  
global_rules:
  - name: "security"
    enabled: true
    rules_text: |
      - Check for SQL injection vulnerabilities
      - Check for XSS vulnerabilities
      - Validate input sanitization
  
  - name: "code_quality"
    enabled: true
    rules_text: |
      - Check for code duplication
      - Ensure proper error handling
      - Check for dead code

file_patterns:
  - pattern: "*.py"
    rules_text: |
      - Follow PEP 8 style guide
      - Use type hints
      - Add docstrings to functions
    llm_config:
      provider: "openai"
      model: "gpt-4o"
      temperature: 0.3

llm:
  provider: "openai"
  model: "gpt-4o"
  temperature: 0.3
  max_tokens: 2000

rag:
  enabled: true
  top_k: 5
  documentation_paths:
    - "docs/"
    - "README.md"
  architectural_docs:
    - "ARCHITECTURE.md"
    - "docs/adr/*.md"
```

## Użycie

### CLI

```bash
# Review pojedynczego Pull Requesta
acr review --pr-url https://github.com/owner/repo/pull/123

# Uruchomienie z lokalną konfiguracją
acr review --pr-url https://github.com/owner/repo/pull/123 --config .acr-config.yml
```

### API Server

```bash
# Uruchomienie serwera
uvicorn acr_system.presentation.api.main:app --reload

# Serwer nasłuchuje webhooków na http://localhost:8000/webhooks/github
```

## Rozwój

### Uruchomienie testów

```bash
# Wszystkie testy
pytest

# Z pokryciem kodu
pytest --cov=acr_system --cov-report=html

# Tylko testy jednostkowe
pytest tests/unit

# Tylko testy integracyjne
pytest tests/integration
```

### Formatowanie i linting

```bash
# Black (formatowanie)
black acr_system tests

# Ruff (linting)
ruff check acr_system tests

# MyPy (type checking)
mypy acr_system
```

### Pre-commit hooks

```bash
pre-commit install
pre-commit run --all-files
```

## Struktura projektu

```
acr_system/
├── domain/              # Warstwa domenowa (entities, value objects, interfaces)
├── ast/                 # Parsowanie AST (tree-sitter)
├── application/         # Use cases i DTOs
├── infrastructure/      # Adaptery (VCS, LLM, RAG, CI)
├── presentation/        # API i CLI
└── shared/              # Współdzielone komponenty
```

## Technologie

- **FastAPI**: REST API
- **Click**: CLI
- **Pydantic**: Walidacja i serializacja
- **OpenAI/Anthropic**: LLM providers
- **FAISS**: Vector store dla RAG
- **Tree-sitter**: Parsowanie AST
- **pytest**: Testy

## Licencja

MIT
