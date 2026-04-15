# Architektura ogolna systemu ACR

## 1. Cel podrozdzialu

Celem podrozdzialu jest przedstawienie architektury ogolnej systemu ACR jako rozwiazania typu end-to-end do automatycznego wspomagania Code Review w workflow PR/MR.

Opis obejmuje:

- podzial odpowiedzialnosci na warstwy,
- granice heksagonalne (porty i adaptery),
- glowne przeplywy wykonawcze (API webhook oraz CLI),
- mechanizmy rozszerzalnosci i miejsca sprzegania z systemami zewnetrznymi.

## 2. Styl architektoniczny i zalozenia

System zostal zaprojektowany jako polaczenie:

1. Clean Architecture (separacja logiki biznesowej od infrastruktury),
2. Hexagonal Architecture / Ports and Adapters (jawne kontrakty dla integracji),
3. orchestracji use-case centrycznej (warstwa application jako koordynator przeplywu).

Najwazniejsze zalozenia architektoniczne:

- logika domenowa pozostaje niezalezna od API VCS, dostawcow LLM i implementacji RAG,
- zaleznosci implementacyjne sa skierowane do wewnatrz (infrastructure -> domain ports),
- zmiana dostawcy (np. GitHub/GitLab, OpenAI/Anthropic) nie wymaga zmian modelu domenowego,
- system moze dzialac zarowno reaktywnie (webhook), jak i wsadowo/manualnie (CLI).

## 3. Widok warstwowy

## 3.1. Warstwa prezentacji

Odpowiada za wejscie do systemu:

- API FastAPI (webhooki),
- CLI (uruchomienia manualne i eksperymentalne).

Warstwa nie implementuje logiki review; deleguje do use-case'ow.

## 3.2. Warstwa aplikacji

Odpowiada za orkiestracje scenariuszy:

- przetworzenie PR/MR,
- publikacja komentarzy,
- indeksacja historii PR,
- ewaluacja eksperymentalna.

To tutaj spinane sa porty domenowe i serwisy domenowe.

## 3.3. Warstwa domenowa

Zawiera:

- encje (np. PullRequest, DiffHunk, ReviewComment, CodeContext),
- value objects (np. Severity, FilePath, LLMConfig, RAGConfig),
- porty (VCSRepository, LLMProvider, EmbeddingStore, StaticAnalyzer, ConfigRepository, CallGraphAnalyzer, ImpactAnalyzer),
- serwisy domenowe (ContextBuilder, ReviewOrchestrator).

Warstwa domenowa definiuje reguly i kontrakty, bez zaleznosci od konkretnej technologii integracyjnej.

## 3.4. Warstwa infrastruktury

Implementuje adaptery do systemow zewnetrznych:

- VCS: GitHubAdapter, GitLabAdapter,
- CI: GitHubChecksAdapter, GitLabCIAdapter,
- LLM: OpenAIAdapter, AnthropicAdapter + LLMProviderFactory,
- RAG: FAISSStore,
- konfiguracja: YAMLConfigLoader.

## 3.5. Warstwa wspolna

Elementy przekrojowe:

- logowanie,
- wyjatki infrastrukturalne,
- narzedzia pomocnicze (np. telemetry/token usage).

## 4. Diagram architektury logicznej (warstwy + porty)

```mermaid
flowchart LR
    subgraph P[Presentation]
        API[FastAPI Webhooks]
        CLI[CLI Commands]
    end

    subgraph A[Application]
        UC1[ProcessPullRequestUseCase]
        UC2[PublishReviewUseCase]
        UC3[IndexPRHistoryUseCase]
        UC4[EvaluatePullRequestUseCase]
    end

    subgraph D[Domain]
        ENT[Entities and Value Objects]
        ORCH[ReviewOrchestrator]
        CTX[ContextBuilder]
        PORTS[Ports Interfaces]
    end

    subgraph I[Infrastructure Adapters]
        VCS[GitHub/GitLab Adapters]
        LLM[OpenAI/Anthropic Adapters]
        RAG[FAISSStore]
        CI[GitHubChecks/GitLabCI]
        CFG[YAML Config Loader]
    end

    API --> UC1
    API --> UC2
    CLI --> UC1
    CLI --> UC2
    CLI --> UC3
    CLI --> UC4

    UC1 --> ORCH
    UC1 --> CTX
    UC1 --> PORTS
    UC2 --> PORTS
    UC3 --> PORTS
    UC4 --> PORTS

    ORCH --> ENT
    CTX --> ENT
    PORTS -.implemented by.-> VCS
    PORTS -.implemented by.-> LLM
    PORTS -.implemented by.-> RAG
    PORTS -.implemented by.-> CI
    PORTS -.implemented by.-> CFG
```

## 5. Granice heksagonalne: porty i adaptery

Kluczowa decyzja architektoniczna polega na tym, ze warstwa domenowa komunikuje sie ze swiatem zewnetrznym wylacznie przez porty.

Przykladowe mapowanie:

- port VCSRepository -> GitHubAdapter / GitLabAdapter,
- port LLMProvider -> OpenAIAdapter / AnthropicAdapter,
- port EmbeddingStore -> FAISSStore,
- port StaticAnalyzer -> GitHubChecksAdapter / GitLabCIAdapter,
- port ConfigRepository -> YAMLConfigLoader (repo) lub FileYAMLConfigLoader (lokalna ewaluacja).

Konsekwencja: system utrzymuje niskie sprzezenie miedzy logika review a API zewnetrznymi.

## 6. Komponent centralny: ReviewOrchestrator

ReviewOrchestrator jest domenowym punktem koordynacji review i wykonuje m.in.:

1. pobranie kontekstu przez ContextBuilder (RAG + surrounding code + historia PR),
2. pobranie i parsowanie sygnalow CI (jesli wlaczono analyzer),
3. wywolanie LLM dla hunkow diff,
4. opcjonalna analize impactu (breaking changes) przez call graph + impact analyzer,
5. agregacje komentarzy.

To podejscie oddziela decyzje domenowe od szczegolow transportu danych.

## 7. Przeplyw glowny: scenariusz webhook (GitHub)

Scenariusz runtime dla pull_request opened/synchronize:

1. Webhook API odbiera event i planuje background task.
2. Task buduje graph zaleznosci (adaptery + serwisy + use-case).
3. ProcessPullRequestUseCase pobiera PR i diff.
4. Ladowana jest konfiguracja .acr-config.yml z repo.
5. Dla plikow/hunkow uruchamiana jest analiza z kontekstem RAG i sygnalami CI.
6. Wynik review jest indeksowany do historii (RAG memory).
7. PublishReviewUseCase publikuje komentarze do PR.

Diagram sekwencji:

```mermaid
sequenceDiagram
    participant GH as GitHub
    participant API as FastAPI Webhook
    participant TASK as Background Task
    participant VCS as GitHubAdapter
    participant CFG as YAMLConfigLoader
    participant ORCH as ReviewOrchestrator
    participant RAG as FAISSStore
    participant LLM as LLMProvider
    participant PUB as PublishReviewUseCase

    GH->>API: pull_request event (opened/synchronize)
    API->>TASK: schedule process_pr_review_task(repo, pr)
    TASK->>VCS: get_pull_request + get_diff_hunks
    TASK->>CFG: load_config(repo, target_branch)
    TASK->>ORCH: review diffs (rules + configs)
    ORCH->>RAG: search_similar(query, top_k)
    ORCH->>VCS: get_file_content(ref=head_sha/source_branch)
    ORCH->>LLM: generate_review_comments(...)
    TASK->>RAG: index_review_history(pr)
    TASK->>PUB: publish(comments)
    PUB->>VCS: post_review_comments
```

## 8. Przeplyw alternatywny: scenariusz CLI

CLI realizuje ten sam rdzen domenowy co API, ale daje dodatkowe tryby:

- review manualny PR/MR,
- index-history (budowa bazy wiedzy z merged PR),
- evaluate (scenariusz eksperymentalny: index + review + raport JSON).

Diagram sekwencji:

```mermaid
sequenceDiagram
    participant U as User
    participant CLI as CLI
    participant UC as ProcessPullRequestUseCase
    participant ORCH as ReviewOrchestrator
    participant RAG as FAISSStore
    participant VCS as VCS Adapter
    participant PUB as PublishReviewUseCase

    U->>CLI: acr review --pr-url ...
    CLI->>UC: execute(PRReviewRequest)
    UC->>VCS: get_pull_request + get_diff_hunks
    UC->>ORCH: review_diff_hunk / review_pull_request
    ORCH->>RAG: retrieve context
    ORCH->>VCS: surrounding code / CI refs
    ORCH-->>UC: review comments
    UC->>RAG: index_review_history(pr)
    CLI-->>U: summary + optional comments
    alt --publish
        CLI->>PUB: execute(ReviewPublishRequest)
        PUB->>VCS: post_review_comments
    end
```

## 9. Konfiguracja i polityki jako element architektury

Konfiguracja .acr-config.yml jest traktowana jako runtime policy:

- aktywacja/dezaktywacja review,
- globalne i per-file rule sets,
- konfiguracja LLM i RAG (global + override per pattern),
- polityka publikacji komentarzy (min_severity, wykluczenia, filtry).

To oznacza, ze czesc decyzji architektonicznych jest przeniesiona do warstwy konfiguracyjnej, bez modyfikacji kodu.

## 10. RAG jako podsystem architektoniczny

FAISSStore realizuje dwa cele:

1. retrieval kontekstu dla biezacego review,
2. inkrementalna pamiec organizacyjna przez index_review_history.

Indeksowane sa m.in.:

- dokumenty architektoniczne,
- historia zmian i dyskusji PR,
- diff-only fallback (gdy brak dyskusji).

W praktyce tworzy to petle uczenia przez kontekst historyczny, bez retrenowania modelu LLM.

## 11. Widok wdrozeniowy (kontekst runtime)

```mermaid
flowchart TB
    DEV[Developer opens/updates PR]
    GH[GitHub or GitLab]
    API[ACR API FastAPI]
    CLI[ACR CLI]
    CORE[Application and Domain Core]
    LLM[(OpenAI or Anthropic API)]
    FAISS[(FAISS Index Storage)]
    CI[(CI Providers / Checks API)]

    DEV --> GH
    GH -->|Webhook| API
    DEV -->|Manual run| CLI

    API --> CORE
    CLI --> CORE

    CORE --> LLM
    CORE --> FAISS
    CORE --> CI
    CORE --> GH
```

## 12. Cechy jakosciowe architektury

Architektura wspiera kluczowe atrybuty jakosciowe:

- modifiability: wymiana adaptera bez zmian domeny,
- testability: mozliwosc testow warstwowych przez porty,
- scalability organizacyjna: osobne punkty wejscia API i CLI,
- observability: centralne logowanie + statystyki tokenow (scenariusze ewaluacyjne),
- governance: kontrola publikacji i standardow przez konfiguracje projektu.

## 13. Ograniczenia i aktualny stan implementacji

- Sciezka GitLab webhook jest zaznaczona, ale bez pelnej analogicznej orkiestracji jak GitHub background flow.
- Publikacja inline na GitLab jest uproszczona (MR notes zamiast pelnego pozycjonowania).
- Jakosc review pozostaje zalezna od jakosci dostarczonego kontekstu i konfiguracji regul.

## 14. Wniosek pod podrozdzial

Architektura ogolna systemu ACR realizuje podejscie heksagonalne z czystym podzialem odpowiedzialnosci i wspolnym rdzeniem domenowym dla API oraz CLI. Dzieki portom i adapterom system laczy integracje VCS, LLM, CI i RAG w jednolity przeplyw review, przy zachowaniu mozliwosci ewolucji technologicznej oraz kontroli polityk projektowych na poziomie konfiguracji.

## 15. Material zrodlowy wykorzystany do opracowania

- [README.md](README.md)
- [architektura-systemu.md](architektura-systemu.md)
- [acr_system/presentation/api/main.py](acr_system/presentation/api/main.py)
- [acr_system/presentation/api/webhook_handlers.py](acr_system/presentation/api/webhook_handlers.py)
- [acr_system/presentation/cli/main.py](acr_system/presentation/cli/main.py)
- [acr_system/application/use_cases/process_pull_request.py](acr_system/application/use_cases/process_pull_request.py)
- [acr_system/application/use_cases/publish_review.py](acr_system/application/use_cases/publish_review.py)
- [acr_system/application/use_cases/index_pr_history.py](acr_system/application/use_cases/index_pr_history.py)
- [acr_system/application/use_cases/evaluate_pull_request.py](acr_system/application/use_cases/evaluate_pull_request.py)
- [acr_system/domain/interfaces/ports.py](acr_system/domain/interfaces/ports.py)
- [acr_system/domain/services/services.py](acr_system/domain/services/services.py)
- [acr_system/infrastructure/llm/llm_factory.py](acr_system/infrastructure/llm/llm_factory.py)
- [acr_system/infrastructure/config/project_config.py](acr_system/infrastructure/config/project_config.py)
- [acr_system/infrastructure/config/yaml_config_loader.py](acr_system/infrastructure/config/yaml_config_loader.py)
- [acr_system/infrastructure/vcs/github_adapter.py](acr_system/infrastructure/vcs/github_adapter.py)
- [acr_system/infrastructure/vcs/gitlab_adapter.py](acr_system/infrastructure/vcs/gitlab_adapter.py)
- [acr_system/infrastructure/ci/github_checks_adapter.py](acr_system/infrastructure/ci/github_checks_adapter.py)
- [acr_system/infrastructure/rag/faiss_store.py](acr_system/infrastructure/rag/faiss_store.py)
