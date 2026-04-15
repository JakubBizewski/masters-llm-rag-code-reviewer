# Macierz sledzenia wymagan systemu ACR

## 1. Cel macierzy

Macierz umozliwia powiazanie wymagania z konkretnym artefaktem implementacyjnym i testowym. Dokument wspiera:

- uzasadnienie spelnienia wymagan w pracy magisterskiej,
- szybka audytowalnosc stanu projektu,
- identyfikacje luk miedzy wymaganiami a implementacja.

## 2. Skala statusu

- Zrealizowane: wymaganie zaimplementowane i potwierdzone.
- Czesciowe: istnieje implementacja bazowa, wymagane dopracowanie.
- Planowane: wymaganie zidentyfikowane, brak pelnej implementacji.

## 3. Macierz FR (wymagania funkcjonalne)

| ID | Wymaganie | Komponenty implementacyjne | Dowody testowe/dokumentacyjne | Status |
|---|---|---|---|---|
| FR-01 | Pobranie i normalizacja danych PR/MR | domain/interfaces/ports.py (VCSRepository), infrastructure/vcs/github_adapter.py, infrastructure/vcs/gitlab_adapter.py | testy unit/integration adapterow VCS, architektura-systemu.md | Zrealizowane |
| FR-02 | Ladowanie konfiguracji .acr-config.yml | infrastructure/config/yaml_config_loader.py, infrastructure/config/project_config.py | testy config loadera, README (sekcja konfiguracji) | Zrealizowane |
| FR-03 | Dopasowanie regul per plik | infrastructure/config/project_config.py (get_rules_for_file) | testy jednostkowe konfiguracji patternow | Zrealizowane |
| FR-04 | Generowanie komentarzy LLM dla hunkow | domain/interfaces/ports.py (LLMProvider), domain/services/services.py (ReviewOrchestrator), infrastructure/llm/* | testy orchestratora i providerow | Zrealizowane |
| FR-05 | Budowanie kontekstu RAG | domain/services/services.py (ContextBuilder), infrastructure/rag/faiss_store.py | test_rag_retrieval_flow.py | Zrealizowane |
| FR-06 | Integracja wynikow CI/CD | infrastructure/ci/github_checks_adapter.py, infrastructure/ci/gitlab_ci_adapter.py, LLM parse_ci_output | test_pr_review_with_ci.py | Zrealizowane bazowo |
| FR-07 | Impact analysis (breaking changes) | CallGraphAnalyzer + ImpactAnalyzer ports, infrastructure/analysis/*, ReviewOrchestrator._perform_impact_analysis | docs/IMPACT_ANALYSIS_TESTS_STATUS.md (42/42) | Zrealizowane |
| FR-08 | Publikacja komentarzy z polityka filtrowania | application/use_cases/publish_review.py, PublishConfig w project_config.py, CLI publish flow | testy publish policy/use case | Zrealizowane |
| FR-09 | Interfejs CLI | presentation/cli/main.py | testy komend CLI, README (uzycie) | Zrealizowane |
| FR-10 | Interfejs API/webhook | presentation/api/main.py, presentation/api/webhook_handlers.py | testy endpointow API i webhookow | Czesciowe (GitHub pelne, GitLab trigger bazowy) |
| FR-11 | Indeksacja historii PR | application/use_cases/index_pr_history.py, EmbeddingStore.index_review_history | testy integracyjne indexowania historii | Zrealizowane |
| FR-12 | Ewaluacja eksperymentalna | application/use_cases/evaluate_pull_request.py, experimental/metrics.py, experimental/reporting.py | raporty JSON i testy modulu eksperymentalnego | Zrealizowane (badawczo) |

## 4. Macierz NFR (wymagania niefunkcjonalne)

| ID | Wymaganie | Wskazniki / kryteria | Artefakty | Status |
|---|---|---|---|---|
| NFR-01 | Modułowosc i separacja | clean architecture, porty/adapters, DIP | struktura katalogow + ports.py | Zrealizowane |
| NFR-02 | Testowalnosc | testy unit/integration, mockowalnosc portow | tests/unit, tests/integration, docs/IMPACT_ANALYSIS_TESTS_STATUS.md | Zrealizowane wysokie |
| NFR-03 | Wydajnosc | async parallelism, limity top_k/history, bounded concurrency | ProcessPullRequestUseCase, IndexPRHistoryUseCase, FAISS config | Zrealizowane bazowo |
| NFR-04 | Niezawodnosc | graceful fallback, wyjatki infrastrukturalne, partial failure tolerance | YAMLConfigLoader fallback, infrastructure_exceptions.py, gather(return_exceptions=True) | Zrealizowane bazowo |
| NFR-05 | Obserwowalnosc | central logging, format logow, brak duplikacji | shared/logging/logger.py | Zrealizowane |
| NFR-06 | Bezpieczenstwo integracji | auth przez app/token, sekrety env, webhook verification, rate limiting | github_jwt auth, env vars; TODO dla podpisow/rate limit | Czesciowe |
| NFR-07 | Konfigurowalnosc | YAML: rules/LLM/RAG/impact/publish policy | project_config.py, yaml_config_loader.py | Zrealizowane |
| NFR-08 | Przenaszalnosc | Python 3.11+, pyproject, API + CLI | pyproject.toml, README | Zrealizowane |
| NFR-09 | Jakosc komentarzy AI | context augmentation, CI grounding, publication filtering, metryki eksperymentalne | ContextBuilder, CI adapters, PublishConfig, EvaluatePullRequestUseCase | Zrealizowane bazowo |

## 5. Luki i rekomendacje do sekcji "dalsze prace"

1. Domkniecie zabezpieczen webhook (weryfikacja sygnatur, rate limiting).
2. Rozszerzenie E2E dla scenariuszy produkcyjnych GitHub i GitLab.
3. Ujednolicenie metryk jakosci komentarzy AI na poziomie CI/CD.
4. Dalsza optymalizacja kosztu tokenowego dla duzych PR (adaptacyjne top_k i chunking).

## 6. Gotowy fragment do cytowania w pracy

"Wymagania funkcjonalne systemu ACR zostaly odwzorowane na porty domenowe i przypadki uzycia, co zapewnia jednoznaczna relacje miedzy specyfikacja a implementacja. Wymagania niefunkcjonalne pokrywaja kluczowe atrybuty jakosci: modularnosc, testowalnosc, niezawodnosc, bezpieczenstwo i konfigurowalnosc. Macierz sledzenia potwierdza, ze funkcje krytyczne (review orchestration, RAG, CI grounding, publikacja komentarzy) sa zrealizowane, a obszary ryzyka ograniczaja sie glownie do twardych mechanizmow security i pelnych testow E2E." 
