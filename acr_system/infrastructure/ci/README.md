# GitHub Checks Adapter

Adapter do pobierania wyników CI/CD z GitHub Checks API.

## Architektura

Zgodnie z zasadami Clean Architecture, adapter ma jedną odpowiedzialność: **zbieranie raw outputs** z różnych narzędzi CI/CD. **Parsowanie i interpretacja** wyników jest delegowane do małego modelu LLM (GPT-4o-mini / Claude-3-Haiku).

### Flow

```
GitHubChecksAdapter → CIToolResult (raw output)
                    ↓
        LLMProvider.parse_ci_output() (GPT-4o-mini)
                    ↓
        ParsedCIIssue (structured, filtered)
                    ↓
        ReviewOrchestrator (main GPT-4o)
                    ↓
        ReviewComment (final output)
```

## Funkcjonalność

- **Pobieranie check runs** dla PR lub konkretnego commita
- **Zbieranie raw outputs** z różnych narzędzi (Ruff, mypy, ESLint, pytest, etc.)
- **Ekstrakcja annotations** - linia/poziom błędów
- **Filtrowanie** - pomija check runs "in progress" i zakończone sukcesem
- **Uniwersalność** - nie zakłada formatu output (text, JSON, logs - wszystko obsługiwane)

## Użycie

```python
from acr_system.infrastructure.ci.github_checks_adapter import GitHubChecksAdapter

# Inicjalizacja
adapter = GitHubChecksAdapter(token="ghp_your_token")

# Pobranie wyników CI dla PR
results = await adapter.fetch_ci_results(
    repo="owner/repo",
    pr_number=123
)

# Lub dla konkretnego commita
results = await adapter.get_check_runs(
    repo="owner/repo",
    commit_sha="abc123def456"
)

# Cleanup
await adapter.close()
```

## Wynik

Zwraca listę `CIToolResult` z **raw outputs**:

```python
CIToolResult(
    tool_name="Ruff",
    status="failure",  # success, failure, warning, skipped
    raw_output="src/main.py:10:1: F401 unused import\nsrc/utils.py:20:5: E501 line too long",
    files_mentioned={"src/main.py", "src/utils.py"},
    conclusion="failure"  # GitHub conclusion
)
```

## Parsowanie przez LLM

Po zebraniu raw outputs, `ReviewOrchestrator` używa **małego modelu LLM** do parsowania:

```python
# W ReviewOrchestrator
for ci_result in ci_results:
    parsed_issues = await llm_provider.parse_ci_output(
        ci_result=ci_result,
        changed_files=pr.changed_files
    )
```

### Dlaczego LLM zamiast dedykowanych parserów?

1. **Uniwersalność** - działa z dowolnym formatem (text, JSON, logs, custom)
2. **Inteligentne filtrowanie** - LLM rozumie context i filtruje tylko relevantne issues
3. **Rozszerzalność** - nowe narzędzia działają od razu, bez pisania parserów
4. **Wykrywanie false positives** - LLM może ocenić czy issue jest prawdziwy
5. **Sugestie fixów** - LLM może zaproponować rozwiązania
6. **Open/Closed Principle** - adapter nie wymaga modyfikacji dla nowych narzędzi

### Przykład parsowania

**Input (CIToolResult):**
```
Ruff output:
src/main.py:10:1: F401 'typing.Optional' imported but unused
src/main.py:25:5: E501 line too long (92 > 88 characters)
tests/test_utils.py:15:10: W291 trailing whitespace
```

**Output (ParsedCIIssue) - tylko dla changed files:**
```python
[
    ParsedCIIssue(
        tool_name="Ruff",
        file_path="src/main.py",
        line_number=10,
        severity="error",
        issue_code="F401",
        message="'typing.Optional' imported but unused",
        suggestion="Remove unused import or use it in type hints"
    ),
    ParsedCIIssue(
        tool_name="Ruff",
        file_path="src/main.py",
        line_number=25,
        severity="warning",
        issue_code="E501",
        message="line too long (92 > 88 characters)",
        suggestion="Break line into multiple lines or use shorter variable names"
    )
]
```

Zwróć uwagę: issue z `tests/test_utils.py` został **odfiltrowany** przez LLM, bo nie jest w `changed_files`.

## Annotations

Adapter automatycznie pobiera annotations z GitHub Checks API:

```python
{
    "path": "src/main.py",
    "start_line": 10,
    "annotation_level": "failure",
    "message": "F401: Unused import 'typing'"
}
```

Annotations są włączane do `raw_output` dla późniejszego parsowania przez LLM.

## Integracja z ProcessPullRequestUseCase

```python
from acr_system.application.use_cases.process_pull_request import ProcessPullRequestUseCase

use_case = ProcessPullRequestUseCase(
    vcs_repository=vcs_adapter,
    llm_provider=llm_provider,  # Zawiera parse_ci_output()
    embedding_store=embedding_store,
    config_repository=config_loader,
    static_analyzer=ci_adapter,  # GitHubChecksAdapter
)

result = await use_case.execute(request)
```

Use case automatycznie:
1. Pobiera raw outputs CI przez `static_analyzer.fetch_ci_results()`
2. Parsuje outputs przez `llm_provider.parse_ci_output()` (GPT-4o-mini)
3. Filtruje issues do tylko changed files
4. Przekazuje parsed CI issues do głównego review LLM (GPT-4o)
5. Generuje skonsolidowane komentarze review

## GitHub API Endpoints

Adapter używa:

- `GET /repos/{owner}/{repo}/pulls/{pr_number}` - informacje o PR
- `GET /repos/{owner}/{repo}/commits/{sha}/check-runs` - check runs
- `GET /repos/{owner}/{repo}/check-runs/{id}/annotations` - annotations

## Wymagania

- GitHub token z uprawnieniem `repo` (do prywatnych repo) lub bez tokenu dla publicznych
- Rate limit: 5000 requests/hour (authenticated)

## Testowanie

```bash
# Testy jednostkowe adaptera (zbieranie raw outputs)
pytest tests/unit/test_github_checks_adapter.py

# Testy LLM parsowania
pytest tests/unit/test_openai_adapter.py -k "parse_ci"

# Testy integracyjne (end-to-end flow)
pytest tests/integration/test_pr_review_with_ci.py
```

## Obsługiwane formaty CI output

Adapter jest **formatem-agnostyczny** - działa z dowolnym formatem:

### Text format (Ruff, mypy)
```
src/main.py:10:1: F401 unused import
src/main.py:25:5: E501 line too long
```

### JSON format (ESLint, niektóre modern tools)
```json
{
  "files": [
    {"path": "src/app.js", "messages": [...]}
  ]
}
```

### Plain logs (pytest, coverage)
```
Coverage report:
TOTAL: 42% coverage
Missing coverage in: src/handlers/auth.py
```

### Custom/proprietary formats
LLM radzi sobie z dowolnym formatem - wystarczy że zawiera informacje o plikach/liniach/błędach.

## Obsługiwane statusy check runs

GitHub Checks API zwraca różne statusy:

**Status:**
- `queued` - w kolejce
- `in_progress` - w trakcie wykonywania
- `completed` - zakończone

**Conclusion (dla completed):**
- `success` - sukces (pomijane przez adapter)
- `failure` - błąd
- `neutral` - neutral (mapowane na "warning")
- `cancelled` - anulowane
- `skipped` - pominięte
- `timed_out` - timeout
- `action_required` - wymaga akcji

Adapter pomija check runs które nie są `completed` lub zakończyły się `success`.

## Rozszerzanie

### Dodanie nowego CI tool

**Nie wymaga zmian w kodzie!** Adapter automatycznie zbiera output z każdego check run w GitHub.

Jeśli używasz custom CI tool:

1. Upewnij się że publikuje wyniki jako GitHub Check Run
2. Raw output pojawi się automatycznie w `CIToolResult`
3. LLM automatycznie go zparsuje

### Przykład: Custom security scanner

```yaml
# .github/workflows/security.yml
name: Security Scan
on: pull_request

jobs:
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run custom scanner
        run: |
          # Twój custom scanner
          ./my-security-tool scan --output=github
```

Jeśli scanner publikuje output jako stdout/annotations w GitHub Check - adapter go automatycznie zbierze i LLM zparsuje!

## Literatura

System parsowania CI przez LLM jest inspirowany:

- **Meng2025RARe**: RAG retrieval z FAISS (top-1 to top-5)
- **Pornprasit2024**: Użycie pomocniczego LLM do parsowania CI outputs  
- **Architektura systemu ACR**: Clean Architecture + Ports & Adapters
