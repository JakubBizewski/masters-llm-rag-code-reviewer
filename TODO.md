# TODO - ACR System Implementation

Lista zadań do ukończenia, aby system był w 100% gotowy do produkcji.

## 🔴 Kluczowe (Essential)

### Infrastructure Layer - Brakujące Adaptery

- [x] **YAML Config Loader** - `infrastructure/config/yaml_config_loader.py`
  - ✅ Implementacja `ConfigRepository` interface
  - ✅ Ładowanie `.acr-config.yml` z repozytorium przez VCS API
  - ✅ Parsowanie YAML do `ProjectConfig`
  - ✅ Walidacja konfiguracji
  - ⚠️ Cache'owanie konfiguracji (optional dla MVP)

- [x] **GitLab Adapter** - `infrastructure/vcs/gitlab_adapter.py`
  - ✅ Implementacja `VCSRepository` dla GitLab
  - ✅ Obsługa Merge Requests (odpowiednik PR)
  - ✅ Parsowanie diff'ów
  - ✅ Publikowanie komentarzy
  - ✅ Pobieranie zawartości plików
  - ✅ Testy jednostkowe (5 tests)

- [x] **Anthropic (Claude) Adapter** - `infrastructure/llm/anthropic_adapter.py`
  - ✅ Implementacja `LLMProvider` dla Claude
  - ✅ Generowanie komentarzy review
  - ✅ Parsowanie CI output
  - ✅ Obsługa różnych modeli Claude (opus, sonnet, haiku)
  - ✅ Testy jednostkowe (18 tests)

- [x] **GitHub Checks Adapter** - `infrastructure/ci/github_checks_adapter.py`
  - ✅ Implementacja `StaticAnalyzer` dla GitHub Checks API
  - ✅ Pobieranie wyników check runs
  - ✅ Parsowanie różnych formatów (Ruff, mypy, ESLint, etc.)
  - ✅ Testy

- [x] **GitLab CI Adapter** - `infrastructure/ci/gitlab_ci_adapter.py`
  - ✅ Implementacja `StaticAnalyzer` dla GitLab CI
  - ✅ Pobieranie artifacts i logów (trace log per job, max 30k chars)
  - ✅ Parsowanie wyników CI/CD (MR pipeline → jobs)
  - ✅ Testy jednostkowe (5 tests)

### AST Parsing (Tree-sitter)

- [x] **AST Parser Interface** - `ast/parser.py`
  - ✅ Definicja `ASTParser` port
  - ✅ Metody do parsowania kodu
  - ✅ Ekstrakcja funkcji, klas, importów

- [x] **Tree-sitter Adapter** - `ast/tree_sitter_adapter.py`
  - ✅ Implementacja parsera używając tree-sitter
  - ✅ Inicjalizacja parserów dla różnych języków
  - ✅ Testy

- [x] **Language Strategies** - `ast/strategies/`
  - ✅ `python_strategy.py` - strategia dla Python
  - ✅ `javascript_strategy.py` - strategia dla JavaScript
  - ✅ `typescript_strategy.py` - strategia dla TypeScript
  - ✅ `go_strategy.py` - strategia dla Go
  - ✅ Language registry (OCP - Open/Closed Principle)

### Impact Analysis (Call Tree / Import Tree) ✅ COMPLETE

**Cel:** Wykrywanie potencjalnych skutków ubocznych zmian przez analizę zależności (1 poziom głębi).

**Status:** ✅ **FULLY IMPLEMENTED & TESTED (42/42 tests passing = 100%)**

**Flow:**
1. Wykryto zmianę metody/funkcji/klasy (z AST)
2. Za pomocą call tree/import tree szukamy kodu który może być dotknięty zmianą
3. LLM analizuje czy zmiana może mieć złe skutki (breaking changes)
4. Jeśli tak, dodajemy komentarz z ostrzeżeniem

- [x] **Dependency Analyzer Interface** - `domain/interfaces/ports.py`
  - ✅ **Refactored to 2 separate ports (SRP compliance):**
  
  **1. CallGraphAnalyzer Port** (technical - grep + tree-sitter):
  - ✅ `find_callers()` - kto wywołuje daną funkcję (1 poziom)
  - ✅ `find_importers()` - kto importuje dany moduł
  - ✅ Pure static analysis - NO LLM required
  - ✅ Reusable for visualization, metrics, etc.
  
  **2. ImpactAnalyzer Port** (semantic - LLM analysis):
  - ✅ `analyze_impact()` - analiza wpływu zmiany (z LLM)
  - ✅ Semantic understanding of breaking changes
  - ✅ Explicit LLM dependency
  - ✅ Generates fix suggestions
  
  - ✅ Value objects: `CallSite`, `ImportSite`, `ImpactAnalysisResult`, `BreakingChange`
  - ✅ Entity: `FunctionNode` (dodano do entities.py)
  - ✅ Exception: `AnalysisError` (dodano do infrastructure_exceptions.py)
  - ✅ Tests: Unit tests dla value objects (test_value_objects.py)

- [x] **Call Graph Analyzer Adapter** - `infrastructure/analysis/tree_sitter_call_graph_analyzer.py`
  - ✅ Implementacja `CallGraphAnalyzer` używając tree-sitter + grep
  - ✅ Grep search dla szybkiego znalezienia candidates
  - ✅ Tree-sitter validation (filter false positives)
  - ✅ Context extraction (5 linii wokół call site)
  - ✅ NO LLM dependency - pure technical analysis

- [x] **Impact Analyzer Adapter** - `infrastructure/analysis/llm_impact_analyzer.py`
  - ✅ Implementacja `ImpactAnalyzer` używając LLM
  - ✅ Requires `LLMProvider` dependency (injected)
  - ✅ LLM prompt building dla impact analysis
  - ✅ Parse LLM response (JSON) → ImpactAnalysisResult
  - ✅ Breaking change detection + fix suggestions

- [x] **Integration z ReviewOrchestrator**
  - ✅ Extended `review_pull_request()` o impact analysis flow
  - ✅ Step 4b: Extract changed functions → **CallGraphAnalyzer**.find_callers()
  - ✅ Step 4c: **ImpactAnalyzer**.analyze_impact() (breaking changes?)
  - ✅ Step 4d: Create warning comments jeśli wykryto problemy
  - ✅ CommentSource.IMPACT_ANALYSIS
  - ✅ Injected both: `CallGraphAnalyzer` + `ImpactAnalyzer` (2 dependencies)

- [x] **Konfiguracja Impact Analysis**
  - ✅ Dodano `impact_analysis` sekcję do `.acr-config.yml`
  - ✅ `enabled: true/false`
  - ✅ `max_callers_per_function: 10` (limit dla performance)
  - ✅ `depth: 1` (tylko direct callers, nie recursive)
  - ✅ `analyze_imports: true/false`
  - ✅ `severity_threshold: medium` (publikuj tylko >= medium)
  - ✅ `exclude_patterns: ["tests/**"]` (nie analizuj test files)

- [x] **Testy Impact Analysis**
  - ✅ Unit tests: `test_tree_sitter_call_graph_analyzer.py` (20 tests, 100% passing)
    * ✅ Test find_callers() dla różnych języków (Python, JavaScript)
    * ✅ Test find_importers() z różnymi import styles
    * ✅ Test false positive filtering (comments, strings, definitions)
    * ✅ Mock grep + tree-sitter (simplified mocking strategy)
  - ✅ Unit tests: `test_llm_impact_analyzer.py` (15 tests, 100% passing)
    * ✅ Test analyze_impact() z różnymi scenariuszami
    * ✅ Test severity parsing i JSON handling
    * ✅ Test error handling
  - ✅ Integration tests: `test_impact_analysis_integration.py` (7 tests, 100% passing)
    * ✅ Test breaking change detection w pełnym flow
    * ✅ Test LLM prompt generation quality
    * ✅ Test warning comment formatting
    * ✅ Test multiple changed functions
  - [ ] Performance tests: benchmark dla dużych repo (optional dla MVP)

- [x] **Dokumentacja Impact Analysis**
  - ✅ Comprehensive test status documentation: `docs/IMPACT_ANALYSIS_TESTS_STATUS.md`
  - ✅ Test coverage: 42/42 tests passing (100%)
  - ✅ Implementation bugs fixed: 20+ issues discovered and resolved
  - ✅ Examples of breaking change scenarios in tests
  - ✅ Simplified mocking strategy documented
  - [ ] Add flow diagram (changed function → find callers → LLM analysis → warning) - optional
  - [ ] Update `acr_system/ast/README.md` with more examples - optional

**Literatura:**
- Ren2025HydraReviewer (call graph analysis)
- Meng2025RARe (context expansion przez dependency tracking)
- Pornprasit2024FineTuningPromptingCR (function isolation)

**Korzyści:**
- 🎯 Wykrycie breaking changes przed merge
- 🎯 Reduced regression (mniej bugów po deploy)
- 🎯 Cross-file awareness (nie tylko diff)
- 🎯 Proactive review z konkretymi fix suggestions

**Trade-offs:**
- ⚠️ Performance overhead (grep + AST parsing)
- ⚠️ Dodatkowe wywołania LLM (koszt)
- ⚠️ False positives (funkcje o tej samej nazwie)

**Mitigation:**
- Limit do top-5 most changed functions
- Cache callers (TTL 1h)
- Tylko depth=1 (nie recursive)
- Configurable: enable/disable per-project

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

- [x] **Unit Tests** - `tests/unit/`
  - ✅ `test_anthropic_adapter.py` (18 tests)
  - ✅ `test_openai_adapter.py`
  - ✅ `test_github_checks_adapter.py`
  - ✅ `test_gitlab_adapter.py` (5 tests)
  - ✅ `test_gitlab_ci_adapter.py` (5 tests)
  - ✅ `test_github_jwt.py`
  - ✅ `test_entities.py`
  - ✅ `test_value_objects.py`
  - ✅ `test_llm_impact_analyzer.py` (15 tests)
  - ✅ `test_tree_sitter_call_graph_analyzer.py` (20 tests)
  - ✅ `test_experimental_metrics.py` (4 tests)
  - ✅ `test_faiss_store_history_indexing.py` (4 tests)
  - ✅ `test_publish_config.py` (3 tests)

- [x] **Integration Tests** - `tests/integration/`
  - ✅ Test pełnego flow review PR (test_full_pr_review_flow.py - 4 tests)
  - ✅ Test integracji z mock'owanymi external API (test_external_api_integration.py - 5 tests)
  - ✅ Test RAG retrieval flow (test_rag_retrieval_flow.py - 6 tests, 100% passing)
  - ✅ Test CI parsing flow (test_pr_review_with_ci.py - enhanced with 4 additional tests)
  - ✅ Test Impact Analysis integration (test_impact_analysis_integration.py - 7 tests, 100% passing)
  - **Status**: 25 integration tests, 13+ passing (some require optional dependency installation)

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

- [ ] **Multi-file Context** (partially covered by Impact Analysis)
  - ~~Wykrywanie breaking changes w API~~ (✅ covered by Impact Analysis)
  - ~~Cross-file dependency analysis~~ (✅ covered by Impact Analysis)
  - Analiza zmian w kontekście wielu plików (advanced)
  - Cross-module impact analysis (beyond 1 level depth)

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

- [ ] Test coverage ≥ 80%
- [x] Wszystkie kluczowe adaptery zaimplementowane (GitHub ✅, GitLab ✅, OpenAI ✅, Anthropic ✅, GitHub Checks ✅, GitLab CI ✅)
- [ ] Security audit passed (webhook verification, rate limiting)
- [ ] Documentation complete (API, deployment, user guide)
- [ ] CI/CD pipeline w pełni functional
- [ ] Load testing passed (100 concurrent reviews)
- [ ] Error rate < 1% w production testing
- [ ] P95 latency < 30s dla review completion
- [ ] Successfully reviewed ≥100 real PRs bez major issues

## 🚀 Roadmap

### Faza 1: MVP ✅ DONE
- ~~Implementacja YAMLConfigLoader~~ ✅
- ~~Dokończenie testów jednostkowych~~ ✅
- Basic webhook security — ❌ remaining
- Deployment documentation — ❌ remaining

### Faza 2: Production Ready — MOSTLY DONE
- ~~GitLab adapter~~ ✅
- ~~Anthropic adapter~~ ✅
- ~~CI adapters (GitHub Checks, GitLab CI)~~ ✅
- ~~Integration tests~~ ✅
- GitHub Actions CI/CD — ❌ remaining
- Monitoring i metrics — ❌ remaining

### Faza 3: Advanced Features ✅ DONE
- ~~AST parsing z tree-sitter~~ ✅
- ~~Impact Analysis (Call Tree / Import Tree)~~ ✅ (42/42 tests passing)
- Advanced RAG (hybrid search, re-ranking) — Nice to have
- Multi-file context — Nice to have
- Learning from feedback — Nice to have
- Performance optimizations — Nice to have

### Faza 4: Scale & Polish — OUT OF SCOPE (thesis complete)
- Queue system
- Database support
- Admin dashboard
- Load testing
- Production deployment

## 📝 Notatki

### Priorytety na teraz:
1. **YAMLConfigLoader** - ✅ Done
2. **AST Parsing** - ✅ Done (tree-sitter + 4 languages)
3. **Impact Analysis** - ✅ Done (42/42 tests passing = 100%)
4. **All core adapters** - ✅ Done (GitHub, GitLab, OpenAI, Anthropic, GitHub Checks, GitLab CI)
5. **Webhook security** - ❌ Not implemented; required before any public deployment
6. **CI/CD** - ❌ No GitHub Actions yet (.github/ missing)

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

**Ostatnia aktualizacja**: 2026-06-10
**Status**: 🟢 Wszystkie kluczowe adaptery zaimplementowane; brakuje webhook security i CI/CD pipeline
**Następny milestone**: Webhook signature verification + GitHub Actions CI workflow
