# TODO - ACR System Implementation

Lista zadań do ukończenia, aby system był w 100% gotowy do produkcji.

## 🔴 Kluczowe (Essential)

### Infrastructure Layer - Brakujące Adaptery

- [ ] **YAML Config Loader** - `infrastructure/config/yaml_config_loader.py`
  - Implementacja `ConfigRepository` interface
  - Ładowanie `.acr-config.yml` z repozytorium przez VCS API
  - Parsowanie YAML do `ProjectConfig`
  - Walidacja konfiguracji
  - Cache'owanie konfiguracji

- [ ] **GitLab Adapter** - `infrastructure/vcs/gitlab_adapter.py`
  - Implementacja `VCSRepository` dla GitLab
  - Obsługa Merge Requests (odpowiednik PR)
  - Parsowanie diff'ów
  - Publikowanie komentarzy
  - Pobieranie zawartości plików
  - Testy jednostkowe i integracyjne

- [ ] **Anthropic (Claude) Adapter** - `infrastructure/llm/anthropic_adapter.py`
  - Implementacja `LLMProvider` dla Claude
  - Generowanie komentarzy review
  - Parsowanie CI output
  - Obsługa różnych modeli Claude (opus, sonnet, haiku)
  - Testy

- [x] **GitHub Checks Adapter** - `infrastructure/ci/github_checks_adapter.py`
  - ✅ Implementacja `StaticAnalyzer` dla GitHub Checks API
  - ✅ Pobieranie wyników check runs
  - ✅ Parsowanie różnych formatów (Ruff, mypy, ESLint, etc.)
  - ✅ Testy

- [ ] **GitLab CI Adapter** - `infrastructure/ci/gitlab_ci_adapter.py`
  - Implementacja `StaticAnalyzer` dla GitLab CI
  - Pobieranie artifacts i logów
  - Parsowanie wyników CI/CD
  - Testy

### AST Parsing (Tree-sitter)

- [ ] **AST Parser Interface** - `ast/parser.py`
  - Definicja `ASTParser` port
  - Metody do parsowania kodu
  - Ekstrakcja funkcji, klas, importów

- [ ] **Tree-sitter Adapter** - `ast/tree_sitter_adapter.py`
  - Implementacja parsera używając tree-sitter
  - Inicjalizacja parserów dla różnych języków
  - Testy

- [ ] **Language Strategies** - `ast/strategies/`
  - `python_strategy.py` - strategia dla Python
  - `javascript_strategy.py` - strategia dla JavaScript
  - `typescript_strategy.py` - strategia dla TypeScript
  - `go_strategy.py` - strategia dla Go
  - Language registry (OCP - Open/Closed Principle)

### Security

- [ ] **Webhook Signature Verification**
  - GitHub webhook signature verification (HMAC)
  - GitLab webhook token verification
  - Middleware dla FastAPI
  - Testy security

- [ ] **Rate Limiting**
  - Rate limiting dla API endpoints
  - Per-IP i per-token rate limits
  - Redis backend (opcjonalnie)
  - Backoff strategy dla LLM API calls

- [ ] **Secrets Management**
  - Walidacja że API keys są ustawione
  - Rotacja tokenów
  - Szyfrowanie secrets w bazie (jeśli używamy)

## 🟠 Ważne (Important)

### Testing

- [ ] **Integration Tests** - `tests/integration/`
  - Test pełnego flow review PR
  - Test integracji z mock'owanymi external API
  - Test RAG retrieval flow
  - Test CI parsing flow

- [ ] **E2E Tests** - `tests/e2e/`
  - Test z rzeczywistym GitHub repository
  - Test webhook delivery
  - Test publikowania komentarzy
  - Wymaga test repository i credentials

- [ ] **Test Coverage**
  - Osiągnięcie 80%+ coverage
  - Coverage reports w CI/CD
  - Integration z codecov.io lub podobnym

### CI/CD

- [ ] **GitHub Actions Workflow** - `.github/workflows/ci.yml`
  - Uruchamianie testów na PR
  - Linting (ruff)
  - Type checking (mypy)
  - Formatowanie (black)
  - Matrix testing (Python 3.11, 3.12)

- [ ] **GitHub Actions - Deployment** - `.github/workflows/deploy.yml`
  - Automatyczny deploy po merge do main
  - Build Docker image
  - Push do registry
  - Deploy do staging/production

### Observability

- [ ] **Structured Logging**
  - Ulepszyć logging z structured fields (JSON)
  - Correlation IDs dla request tracking
  - Log levels configuration per module
  - Integration z systemami jak ELK, Datadog

- [ ] **Metrics & Monitoring**
  - `infrastructure/persistence/metrics_logger.py`
  - Metryki: liczba review, czas wykonania, koszty API
  - Prometheus metrics endpoint
  - Grafana dashboards

- [ ] **Error Tracking**
  - Integration z Sentry lub podobnym
  - Error alerting
  - Performance monitoring
  - User feedback on errors

### Documentation

- [ ] **API Documentation**
  - OpenAPI/Swagger documentation (FastAPI auto-generates)
  - Przykłady webhook payloads
  - Authentication documentation
  - Rate limits documentation

- [ ] **Deployment Guide**
  - Instrukcje deployment na różne platformy
  - Docker Compose setup
  - Kubernetes manifests
  - Environment variables documentation

- [ ] **User Guide**
  - Jak skonfigurować repository
  - Przykłady różnych rule sets
  - Best practices dla tworzenia reguł
  - Troubleshooting guide

- [ ] **Architecture Documentation**
  - Diagramy architektury (C4 model)
  - Sequence diagrams dla głównych flow
  - Decision records (ADR)

## 🟡 Przydatne (Nice to Have)

### Features

- [ ] **Multi-file Context**
  - Analiza zmian w kontekście wielu plików
  - Wykrywanie breaking changes w API
  - Cross-file dependency analysis

- [ ] **Learning from Feedback**
  - Zapisywanie feedbacku o komentarzach (przydatne/nieprzydatne)
  - Używanie feedbacku do RAG improvement
  - Fine-tuning promptów na podstawie feedbacku

- [ ] **Custom LLM Providers**
  - Support dla local LLM (Ollama, llama.cpp)
  - Azure OpenAI adapter
  - Custom API endpoint adapter
  - LLM provider factory pattern

- [ ] **Advanced RAG**
  - Hybrid search (semantic + BM25)
  - Query expansion
  - Re-ranking results
  - Chunking strategies dla długich dokumentów

- [ ] **Review Templates**
  - Predefiniowane template dla różnych typów review
  - Template marketplace/sharing
  - Template versioning

- [ ] **Batch Processing**
  - Review wielu PR naraz
  - Scheduled reviews (np. codziennie o 9:00)
  - Bulk re-review po zmianie reguł

### Infrastructure

- [ ] **Docker Support**
  - `Dockerfile` dla API server
  - `Dockerfile` dla CLI
  - Docker Compose dla local development
  - Multi-stage builds dla mniejszych images

- [ ] **Database Support**
  - Opcjonalny PostgreSQL dla review history
  - Migrations (Alembic)
  - Repository pattern dla persistence
  - Query optimization

- [ ] **Queue System**
  - Celery lub RQ dla background jobs
  - Redis jako message broker
  - Worker scaling
  - Job monitoring dashboard

- [ ] **Caching**
  - Redis cache dla RAG results
  - Cache dla file contents
  - Cache dla LLM responses (z hash key)
  - TTL strategies

### Developer Experience

- [ ] **CLI Improvements**
  - Interactive mode dla review
  - Progress bars dla długich operacji
  - Kolorowy output
  - Config wizard (init command)

- [ ] **API Improvements**
  - GraphQL API (opcjonalnie)
  - WebSocket dla real-time updates
  - Batch operations endpoint
  - Admin dashboard (web UI)

- [ ] **Development Tools**
  - Dev container configuration
  - VS Code extensions recommendations
  - Debug configurations
  - Mock servers dla testowania

### Performance

- [ ] **Optimization**
  - Parallel processing diff hunks
  - LLM request batching
  - Connection pooling
  - Async optimization review

- [ ] **Cost Optimization**
  - Token counting przed wywołaniem LLM
  - Smart chunking żeby zmniejszyć tokeny
  - Caching expensive operations
  - Wybór tańszych modeli dla prostych zadań

## 📊 Metryki Sukcesu

Kryteria uznania systemu za gotowy do produkcji:

- [ ] ✅ Test coverage ≥ 80%
- [ ] ✅ Wszystkie kluczowe adaptery zaimplementowane
- [ ] ✅ Security audit passed (webhook verification, rate limiting)
- [ ] ✅ Documentation complete (API, deployment, user guide)
- [ ] ✅ CI/CD pipeline w pełni functional
- [ ] ✅ Load testing passed (100 concurrent reviews)
- [ ] ✅ Error rate < 1% w production testing
- [ ] ✅ P95 latency < 30s dla review completion
- [ ] ✅ Successfully reviewed ≥100 real PRs bez major issues

## 🚀 Roadmap

### Faza 1: MVP (Minimum Viable Product) - 2 tygodnie
- Implementacja YAMLConfigLoader
- Dokończenie testów jednostkowych
- Basic webhook security
- Deployment documentation

### Faza 2: Production Ready - 4 tygodnie
- GitLab adapter
- Anthropic adapter
- CI adapters (GitHub Checks, GitLab CI)
- Integration tests
- GitHub Actions CI/CD
- Monitoring i metrics

### Faza 3: Advanced Features - 6 tygodni
- AST parsing z tree-sitter
- Advanced RAG
- Multi-file context
- Learning from feedback
- Performance optimizations

### Faza 4: Scale & Polish - 4 tygodnie
- Queue system
- Database support
- Admin dashboard
- Load testing
- Production deployment

## 📝 Notatki

### Priorytety na teraz:
1. **YAMLConfigLoader** - bez tego system nie może załadować konfiguracji
2. **Webhook security** - przed uruchomieniem w produkcji
3. **Tests** - pewność że core functionality działa
4. **CI/CD** - automatyzacja testowania i deployment

### Decyzje do podjęcia:
- [ ] Czy używamy bazy danych czy tylko in-memory store?
- [ ] Jaki queue system: Celery, RQ, czy może AWS SQS?
- [ ] Gdzie hostować: AWS, GCP, Azure, czy self-hosted?
- [ ] Jaki model licencjonowania: open source, freemium, enterprise?

### Zależności zewnętrzne:
- OpenAI API (GPT-4, GPT-4o)
- Anthropic API (Claude)
- GitHub API
- GitLab API
- FAISS (CPU version lub GPU dla scale)
- Tree-sitter parsers dla różnych języków

---

**Ostatnia aktualizacja**: 2026-02-23
**Status**: 🟡 MVP w trakcie implementacji
**Następny milestone**: Faza 1 completion
