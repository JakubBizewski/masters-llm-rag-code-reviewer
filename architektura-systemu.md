# Architektura Systemu ACR - Automated Code Review

## Przegląd architektury

System ACR został zaprojektowany zgodnie z zasadami **Clean Architecture** oraz **architektury heksagonalnej (Ports & Adapters)**. Kluczowe założenia:

- **Separacja warstw**: logika domeny odizolowana od szczegółów implementacyjnych
- **Dependency Inversion**: zależności skierowane do wewnątrz (od infrastruktury do domeny)
- **Testowalność**: możliwość testowania warstw w izolacji
- **Wymienność adapterów**: łatwa zmiana dostawców (GitHub → GitLab, GPT-4 → Claude)

## Struktura katalogów

```
acr_system/
├── domain/                      # Warstwa domenowa (core logic)
│   ├── entities/
│   │   ├── pull_request.py      # Encja PR/MR
│   │   ├── diff_hunk.py         # Fragment zmiany kodu
│   │   ├── review_comment.py    # Komentarz recenzji
│   │   ├── code_context.py      # Kontekst projektu (RAG)
│   │   ├── ci_tool_result.py    # Raw wyniki z CI/CD (różne formaty)
│   │   └── parsed_ci_issue.py   # Sparsowane CI issues (przez helper LLM)
│   ├── value_objects/
│   │   ├── file_path.py         # VO reprezentujący ścieżkę pliku
│   │   ├── language.py          # VO języka programowania
│   │   └── severity.py          # VO poziomu krytyczności
│   ├── interfaces/              # Porty (abstrakcje)
│   │   ├── vcs_repository.py    # Port: repo VCS (GitHub/GitLab)
│   │   ├── llm_provider.py      # Port: dostawca LLM
│   │   ├── embedding_store.py   # Port: baza wektorowa (RAG)
│   │   ├── static_analyzer.py   # Port: fetch CI results (GitHub/GitLab)
│   │   └── config_repository.py # Port: konfiguracja projektu
│   └── services/
│       ├── review_orchestrator.py  # Główny serwis orkiestrujący review
│       └── context_builder.py      # Budowanie kontekstu dla LLM
│
├── ast/
│   ├── parser.py                        # Port ASTParser
│   ├── tree_sitter_adapter.py           # Tree-sitter implementation
│   ├── language_registry.py             # Registry dla strategii języków (OCP)
│   └── strategies/                      # Language strategies (OCP)
│       ├── language_strategy.py         # Abstrakcja LanguageStrategy
│       ├── python_strategy.py           # Strategia dla Python
│       ├── javascript_strategy.py       # Strategia dla JavaScript
│       ├── typescript_strategy.py       # Strategia dla TypeScript
│       └── go_strategy.py               # Strategia dla Go
│
├── application/                 # Warstwa aplikacji (use cases)
│   ├── use_cases/
│   │   ├── process_pull_request.py      # UC: review PR/MR
│   │   ├── retrieve_context.py          # UC: RAG retrieval
│   │   ├── generate_review_comments.py  # UC: generowanie komentarzy
│   │   └── publish_review.py            # UC: publikacja w VCS
│   ├── dto/                     # Data Transfer Objects
│   │   ├── pr_review_request.py
│   │   └── review_result.py
│   └── events/                  # Domain Events
│       ├── pr_opened.py
│       └── review_completed.py
│
├── infrastructure/              # Warstwa infrastruktury (adapters)
│   ├── vcs/                     # Adaptery VCS
│   │   ├── github_adapter.py    # REST API + webhooks GitHub
│   │   ├── gitlab_adapter.py    # REST API + webhooks GitLab
│   │   └── vcs_webhook_parser.py
│   ├── llm/                     # Adaptery LLM
│   │   ├── llm_provider_factory.py  # Factory dla providerów (OCP)
│   │   ├── openai_adapter.py        # OpenAI GPT-4/4o
│   │   ├── anthropic_adapter.py     # Claude
│   │   ├── model_selector.py        # Dobór modelu wg konfiguracji
│   │   └── prompt_template.py       # Szablony promptów
│   ├── rag/                     # Infrastruktura RAG
│   │   ├── faiss_store.py       # FAISS vector store
│   │   ├── bm25_retriever.py    # BM25 leksykalny
│   │   ├── embedding_service.py # Generowanie embeddingów
│   │   └── context_indexer.py   # Indeksowanie dokumentacji/CR
│   ├── ci/                      # Integracja z CI/CD (fetch results)
│   │   ├── github_checks_adapter.py  # Fetch z GitHub Checks API
│   │   └── gitlab_ci_adapter.py      # Fetch z GitLab CI artifacts/logs
│   ├── config/                  # Konfiguracja
│   │   ├── yaml_config_loader.py # Wczytywanie .acr-config.yml
│   │   └── project_config.py    # Model konfiguracji projektu
│   └── persistence/
│       ├── review_history_repo.py # Historia review (do RAG)
│       └── metrics_logger.py      # Logowanie metryk (BLEU itp.)
│
├── presentation/                # Warstwa prezentacji (API/CLI)
│   ├── api/                     # REST API (FastAPI)
│   │   ├── webhook_handlers.py  # Odbieranie webhooków VCS
│   │   ├── health_check.py
│   │   └── admin_api.py         # API administracyjne
│   ├── cli/                     # CLI (Click/Typer)
│   │   ├── review_command.py    # Ręczne uruchomienie review
│   │   └── config_command.py    # Zarządzanie konfiguracją
│   └── schemas/                 # Schematy API (Pydantic)
│       ├── webhook_payload.py
│       └── review_response.py
│
└── shared/                      # Współdzielone komponenty
    ├── logging/
    │   └── structured_logger.py
    ├── exceptions/
    │   ├── domain_exceptions.py
    │   └── infrastructure_exceptions.py
    └── utils/
        ├── retry_decorator.py
        └── telemetry.py
```

---

## Warstwa Domain (Domena)

### Value Objects

**RuleSet**
```python
@dataclass
class RuleSet:
    """Ogólny zestaw zasad code review (security, performance, quality)."""
    name: str
    enabled: bool
    rules_text: str  # Tekst LLM-friendly, nie sztywna struktura
```

**FilePatternRule**
```python
@dataclass
class FilePatternRule:
    """Zasady dla konkretnych patternów plików (glob)."""
    pattern: str     # Glob pattern: *.ts, */Domain/*.cs, **/*.test.ts
    rules_text: str  # Tekst LLM-friendly
    priority: int = 0  # Wyższa wartość = wyższy priorytet (dla konfliktów)
    llm_config: Optional['LLMConfig'] = None  # Override global LLM settings
    rag_config: Optional['RAGConfig'] = None  # Override global RAG settings
```

**LLMConfig**
```python
@dataclass
class LLMConfig:
    """Konfiguracja LLM (global lub per file pattern)."""
    provider: str = "openai"  # openai | anthropic | custom
    model: str = "gpt-4o"
    temperature: float = 0.3
    max_tokens: int = 2000
```

**RAGConfig**
```python
@dataclass
class RAGConfig:
    """Konfiguracja RAG (global lub per file pattern)."""
    enabled: bool = True
    top_k: int = 5
    documentation_paths: List[str] = field(default_factory=list)
    architectural_docs: List[str] = field(default_factory=list)
```

**ArchitecturalDocument**
```python
@dataclass
class ArchitecturalDocument:
    """Dokument architektoniczny z repo (ARCHITECTURE.md, ADR/*.md)."""
    filename: str
    content: str
    last_modified: datetime
```

**CIToolResult**
```python
@dataclass
class CIToolResult:
    """
    Luźno zebrane wyniki z jednego narzędzia CI (Ruff, mypy, ESLint).
    Różne narzędzia = różne formaty. Raw output - wymaga parsowania przez LLM.
    """
    tool_name: str              # "Ruff", "mypy", "ESLint", "pytest"
    status: str                 # "success", "failure", "warning"
    raw_output: str             # Pełny output z narzędzia (text lub JSON)
    files_mentioned: Set[str]   # Pliki wymienione w outputcie (best effort parsing)
    conclusion: str             # "passed", "failed", "skipped"
```

**ParsedCIIssue**
```python
@dataclass
class ParsedCIIssue:
    """
    CI issue sparsowany przez LLM - wyodrębniony z raw output, tylko relevantne dla diff.
    LLM parsing krok: filtruje issues do zmienionych plików/linii.
    """
    tool_name: str              # "Ruff", "mypy", "ESLint"
    file_path: str              # "src/main.py"
    line_number: Optional[int]  # 42 (lub None jeśli ogólny issue)
    severity: str               # "error", "warning", "info"
    issue_code: Optional[str]   # "F401", "E501", "prefer-const"
    message: str                # "Unused import: typing.Optional"
    suggestion: Optional[str]   # Opcjonalna sugestia fix od parsing LLM
    is_in_diff: bool            # True jeśli issue jest w zmienionych liniach
```

**Przykłady różnych formatów CI**:
```python
# Format 1: Structured output z line numbers (GitHub annotations, ESLint JSON)
CIToolResult(
    tool_name="ESLint",
    status="failure",
    raw_output="""src/api/handler.ts:23: error: Prefer const over let (prefer-const)
src/api/handler.ts:45: warning: Unused variable 'result' (no-unused-vars)
src/utils/format.ts:12: error: Missing return type (explicit-function-return-type)""",
    files_mentioned={"src/api/handler.ts", "src/utils/format.ts"},
    conclusion="failed"
)

# Format 2: JSON structured (Ruff --format=json)
CIToolResult(
    tool_name="Ruff",
    status="failure",
    raw_output="""{
  "files": [
    {"path": "main.py", "line": 42, "code": "F401", "message": "Unused import: typing.Optional"},
    {"path": "utils.py", "line": 15, "code": "E501", "message": "Line too long (120 > 88)"}
  ]
}""",
    files_mentioned={"main.py", "utils.py"},
    conclusion="failed"
)

# Format 3: Plain text per file (mypy text output)
CIToolResult(
    tool_name="mypy",
    status="failure",
    raw_output="""
main.py:42: error: Incompatible return value type (got "str", expected "int")
main.py:45: note: See https://mypy.readthedocs.io/en/stable/common_issues.html
utils.py:15: error: Argument 1 has incompatible type "str"; expected "int"
""",
    files_mentioned={"main.py", "utils.py"},
    conclusion="failed"
)

# Format 4: Ogólne logi bez line numbers (niektóre CI jobs)
CIToolResult(
    tool_name="pytest-coverage",
    status="warning",
    raw_output="""
Coverage report:
TOTAL: 42% coverage

Missing coverage in:
- src/handlers/auth.py
- src/utils/validation.py
Required minimum: 80%
""",
    files_mentioned={"src/handlers/auth.py", "src/utils/validation.py"},
    conclusion="failed"
)
```

**Interpretacja przez LLM**:
- **Format 1-3**: LLM ekstraktuje file:line, tworzy kontekstowe komentarze z wyjaśnieniem
- **Format 4**: LLM widzi ogólny problem, sugeruje co zrobić (brak konkretnych linii = ogólny komentarz na PR)
- **Wszystkie**: LLM dodaje wyjaśnienie WHY, sugestie HOW TO FIX, wykrywa false positives

### Entities (Encje)

**1. PullRequest**
```python
@dataclass
class PullRequest:
    id: str
    repository: str
    source_branch: str
    target_branch: str
    author: str
    diff_hunks: List[DiffHunk]
    metadata: Dict[str, Any]
    total_changes: int  # Liczba zmienionych linii
    
    def get_changed_files(self) -> List[FilePath]:
        """Zwraca listę zmienionych plików."""
    
    def get_primary_language(self) -> Language:
        """Określa dominujący język w PR."""
    
    def should_chunk(self, max_lines_per_chunk: int = 500) -> bool:
        """Określa czy PR wymaga chunkowania (duży PR)."""
        return self.total_changes > max_lines_per_chunk
    
    def create_chunks(self, chunk_size: int = 500) -> List['PullRequestChunk']:
        """Dzieli duży PR na mniejsze chunki do przetwarzania."""
        chunks = []
        current_chunk_hunks = []
        current_chunk_size = 0
        
        for hunk in self.diff_hunks:
            hunk_size = len(hunk.added_lines) + len(hunk.removed_lines)
            
            if current_chunk_size + hunk_size > chunk_size and current_chunk_hunks:
                # Commit current chunk
                chunks.append(PullRequestChunk(
                    parent_pr_id=self.id,
                    chunk_index=len(chunks),
                    diff_hunks=current_chunk_hunks.copy(),
                    metadata=self.metadata
                ))
                current_chunk_hunks = []
                current_chunk_size = 0
            
            current_chunk_hunks.append(hunk)
            current_chunk_size += hunk_size
        
        # Last chunk
        if current_chunk_hunks:
            chunks.append(PullRequestChunk(
                parent_pr_id=self.id,
                chunk_index=len(chunks),
                diff_hunks=current_chunk_hunks,
                metadata=self.metadata
            ))
        
        return chunks
```

**2. DiffHunk**
```python
@dataclass
class DiffHunk:
    file_path: FilePath
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    added_lines: List[str]
    removed_lines: List[str]
    context_lines: List[str]
    
    def extract_functions(self, parser: ASTParser, code: str) -> List[FunctionNode]:
        """Ekstrakcja funkcji z diffa (Tree-sitter). Augmentacja kontekstu RAG."""
        language = self._detect_language()
        return parser.extract_changed_functions(self, code, language)
    
    def size(self) -> int:
        """Rozmiar hunka w liniach (added + removed)."""
        return len(self.added_lines) + len(self.removed_lines)
    
    def _detect_language(self) -> Language:
        """Wykrywa język na podstawie rozszerzenia pliku."""
        suffix = self.file_path.suffix.lower()
        language_map = {
            ".py": Language.PYTHON,
            ".js": Language.JAVASCRIPT,
            ".ts": Language.TYPESCRIPT,
            ".go": Language.GO,
            ".java": Language.JAVA,
        }
        return language_map.get(suffix, Language.UNKNOWN)
```

**2a. PullRequestChunk**
```python
@dataclass
class PullRequestChunk:
    """Chunk dużego PR do sekwencyjnego przetwarzania."""
    parent_pr_id: str
    chunk_index: int
    diff_hunks: List[DiffHunk]
    metadata: Dict[str, Any]
    
    def to_diff_string(self) -> str:
        """Serializacja chunka do formatu diff."""
        return "\n".join([hunk.to_string() for hunk in self.diff_hunks])
    
    def total_changes(self) -> int:
        """Łączna liczba zmian w chunku."""
        return sum(hunk.size() for hunk in self.diff_hunks)
```

**3. ReviewComment**
```python
@dataclass
class ReviewComment:
    file_path: FilePath
    line_number: int
    severity: Severity  # INFO, WARNING, ERROR, CRITICAL
    message: str
    source: CommentSource  # LLM, STATIC_ANALYSIS, IMPACT_ANALYSIS, HUMAN
    suggested_fix: Optional[str]
    
    def is_actionable(self) -> bool:
        """Czy komentarz wymaga akcji (human-in-the-loop)?"""
```

**4. CodeContext (RAG)**
```python
@dataclass
class CodeContext:
    documentation_chunks: List[str]  # Retrieved z .md files (ARCHITECTURE.md, ADR/*.md)
    historical_reviews: List[ReviewComment]
    general_rules: List[RuleSet]     # Ogólne zasady (security, performance, etc.)
    file_pattern_rules: List[FilePatternRule]  # Zasady dla glob patterns
    architectural_docs: List[str]    # Full content z .u044d files (ARCHITECTURE.md, CODING_STANDARDS.md)
    parsed_ci_issues: List[ParsedCIIssue]  # CI issues sparsowane przez LLM, tylko relevantne dla diff
    extracted_functions: List[FunctionNode]  # Funkcje wyekstrahowane z diff (Tree-sitter AST)
    similar_prs: List[PullRequest]
    
    def to_prompt_context(self, changed_files: List[FilePath]) -> str:
        """
        Serializacja kontekstu do promptu LLM.
        Zasady jako tekst LLM-friendly (nie sztywne struktury).
        Automatyczne dopasowanie zasad według file patterns.
        """
        context_parts = []
        
        # Ogólne zestawy zasad (security, performance, quality)
        if self.general_rules:
            context_parts.append("# General Code Review Rules\n")
            for rule_set in self.general_rules:
                if rule_set.enabled:
                    context_parts.append(f"## {rule_set.name}\n{rule_set.rules_text}")
        
        # Zasady per file pattern (dopasowane do zmienionych plików)
        matched_patterns = self._match_file_patterns(changed_files)
        if matched_patterns:
            context_parts.append("\n# File-Specific Rules\n")
            for pattern, rules_text in matched_patterns:
                context_parts.append(f"## Pattern: {pattern}\n{rules_text}")
        
        # Wyniki statycznej analizy z CI/CD (sparsowane przez LLM, tylko relevantne)
        if self.parsed_ci_issues:
            context_parts.append("\n# Static Analysis Issues (Parsed from CI/CD)\n")
            context_parts.append(
                "The following issues were detected by CI tools and filtered to only show "
                "problems in changed files/lines. Consider these in your review, add context, "
                "suggest fixes, and detect potential false positives.\n"
            )
            context_parts.append("\n```")
            
            for issue in self.parsed_ci_issues:
                location = f"{issue.file_path}"
                if issue.line_number:
                    location += f":{issue.line_number}"
                
                issue_line = f"[{issue.severity.upper()}] {issue.tool_name}"
                if issue.issue_code:
                    issue_line += f" ({issue.issue_code})"
                issue_line += f": {issue.message}"
                
                context_parts.append(f"- {location}: {issue_line}")
                
                if issue.suggestion:
                    context_parts.append(f"  Suggestion: {issue.suggestion}")
                    
                if not issue.is_in_diff:
                    context_parts.append("  Note: Issue in file but outside changed lines")
            
            context_parts.append("```")
            for pattern_rule in matched_patterns:
                context_parts.append(
                    f"Files matching: `{pattern_rule.pattern}`\n{pattern_rule.rules_text}"
                )
        
        # Wyekstrahowane funkcje z diff (Tree-sitter AST) - context enhancement
        if self.extracted_functions:
            context_parts.append("\n# Extracted Functions from Changed Files (AST)\n")
            context_parts.append(
                "The following functions were extracted from changed files using AST parsing. "
                "Use this to understand the full context of changed code, not just diff fragments.\n"
            )
            context_parts.append("\n```")
            
            for func in self.extracted_functions:
                func_header = f"Function: {func.name} (lines {func.start_line}-{func.end_line})"
                context_parts.append(f"\n### {func_header}")
                context_parts.append(f"```{func.language.value}")
                context_parts.append(func.body)
                context_parts.append("```")
            
            context_parts.append("```")
        
        # Dokumentacja architektoniczna (ARCHITECTURE.md, ADR/*.md z repo)
        if self.architectural_docs:
            context_parts.append("\n# Project Architecture & Standards\n")
            for doc in self.architectural_docs:
                context_parts.append(f"## {doc.filename}\n{doc.content}")
        
        # Retrieved dokumentacja (RAG similarity search)
        if self.documentation_chunks:
            context_parts.append("\n# Relevant Documentation (RAG)\n")
            context_parts.append("\n".join(self.documentation_chunks))
        
        # Historyczne review patterns
        if self.historical_reviews:
            context_parts.append(f"\n# Historical Review Patterns\n{self._format_reviews(self.historical_reviews[:5])}")
        
        return "\n\n".join(context_parts)
    
    def _match_file_patterns(self, changed_files: List[FilePath]) -> List[FilePatternRule]:
        """Dopasowuje zasady file pattern do zmienionych plików (glob matching)."""
        matched = []
        for file_path in changed_files:
            for pattern_rule in self.file_pattern_rules:
                if fnmatch.fnmatch(str(file_path), pattern_rule.pattern):
                    if pattern_rule not in matched:
                        matched.append(pattern_rule)
        return matched
    
    def _format_reviews(self, reviews: List[ReviewComment]) -> str:
        """Formatuje historyczne review do kontekstu."""
        return "\n".join([f"- {r.message}" for r in reviews])
```

**5. Language (Enum)**
```python
from enum import Enum

class Language(Enum):
    """Języki programowania wspierane przez Tree-sitter."""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    GO = "go"
    JAVA = "java"
    UNKNOWN = "unknown"
```

**6. FunctionNode**
```python
@dataclass
class FunctionNode:
    """Funkcja wyekstrahowana z AST (Tree-sitter)."""
    name: str              # Nazwa funkcji
    start_line: int        # Początek funkcji w pliku
    end_line: int          # Koniec funkcji w pliku
    body: str              # Pełne ciało funkcji (kod)
    language: Language     # Język programowania
    
    def size(self) -> int:
        """Rozmiar funkcji w liniach."""
        return self.end_line - self.start_line + 1
```

---

### Interfaces (Porty - abstrakcje)

**Port: VCSRepository**
```python
from abc import ABC, abstractmethod

class VCSRepository(ABC):
    """Abstrakcja dla platformy VCS (GitHub, GitLab)."""
    
    @abstractmethod
    def fetch_pull_request(self, pr_id: str) -> PullRequest:
        """Pobiera PR/MR z platformy."""
    
    @abstractmethod
    def fetch_diff(self, pr_id: str) -> List[DiffHunk]:
        """Pobiera diff dla PR."""
    
    @abstractmethod
    def publish_comments(self, pr_id: str, comments: List[ReviewComment]) -> None:
        """Publikuje komentarze w PR jako inline comments."""
    
    @abstractmethod
    def fetch_historical_reviews(self, repo: str, limit: int) -> List[ReviewComment]:
        """Pobiera historyczne komentarze do RAG."""
    
    @abstractmethod
    def fetch_file(self, repo: str, file_path: str, branch: str = "main") -> str:
        """Pobiera zawartość pojedynczego pliku z repo."""
    
    @abstractmethod
    def list_files(self, repo: str, pattern: str, branch: str = "main") -> List[str]:
        """Listuje pliki pasujące do glob pattern (np. docs/ADR/*.md)."""
```

**Port: LLMProvider**
```python
class LLMProvider(ABC):
    """Abstrakcja dla dostawcy LLM."""
    
    @abstractmethod
    def generate_review(
        self, 
        diff: str, 
        context: CodeContext,
        model_config: ModelConfig
    ) -> List[ReviewComment]:
        """Generuje komentarze review dla danego diffa."""
    
    @abstractmethod
    def parse_ci_output(
        self,
        prompt: str,
        response_format: str = "json"
    ) -> str:
        """
        Parsuje raw CI outputs przez pomocniczy LLM.
        Używa tańszego modelu (GPT-4o-mini, Claude-3-Haiku).
        Zwraca structured JSON z parsed issues.
        """
    
    @abstractmethod
    def estimate_cost(self, input_tokens: int, output_tokens: int, model: str = None) -> float:
        """Estymuje koszt wywołania API. Model parameter dla różnych modeli (GPT-4o vs GPT-4o-mini)."""
```

**Port: EmbeddingStore**
```python
class EmbeddingStore(ABC):
    """Abstrakcja dla bazy wektorowej (RAG)."""
    
    @abstractmethod
    def index_document(self, doc_id: str, text: str, metadata: Dict) -> None:
        """Indeksuje dokument (dokumentacja, CR)."""
    
    @abstractmethod
    def retrieve_top_k(self, query: str, k: int) -> List[Document]:
        """Retrieval top-k dokumentów najbardziej podobnych."""
    
    @abstractmethod
    def clear_index(self, repository: str) -> None:
        """Usuwa indeks dla repozytorium."""
```

**Port: StaticAnalyzer**
```python
class StaticAnalyzer(ABC):
    """Abstrakcja dla pobierania wyników analizy statycznej z CI/CD."""
    
    @abstractmethod
    def fetch_ci_results(self, pr: PullRequest) -> List[CIToolResult]:
        """
        Pobiera luźno zebrane wyniki z CI/CD.
        Różne narzędzia = różne formaty (JSON, text, logs).
        System nie wymusza struktury - LLM sam interpretuje.
        """
    
    @abstractmethod
    def is_ci_completed(self, pr: PullRequest) -> bool:
        """Sprawdza czy CI zakończył działanie (ready to fetch results)."""
```

**Port: ASTParser**
```python
class ASTParser(ABC):
    """Abstrakcja dla parsowania AST i ekstrakcji struktury kodu (Tree-sitter)."""
    
    @abstractmethod
    def extract_functions(self, code: str, language: Language) -> List[FunctionNode]:
        """
        Ekstrakcja funkcji z kodu źródłowego.
        Używane do augmentacji kontekstu RAG (izolacja funkcji, call graph).
        """
    
    @abstractmethod
    def build_call_graph(self, functions: List[FunctionNode]) -> nx.DiGraph:
        """Budowa call graph z funkcji (dla augmentacji promptu)."""
    
    @abstractmethod
    def extract_changed_functions(self, diff: DiffHunk, code: str, language: Language) -> List[FunctionNode]:
        """Ekstrakcja tylko funkcji zmienionych w diff (context enhancement)."""
```

---

### Domain Services

**ReviewOrchestrator**
```python
class ReviewOrchestrator:
    """Główny serwis domenowy orkiestrujący proces review."""
    
    def __init__(
        self,
        vcs_repo: VCSRepository,
        llm_provider: LLMProvider,
        embedding_store: EmbeddingStore,
        static_analyzer: StaticAnalyzer,
        ast_parser: ASTParser,
        config_repo: ConfigRepository
    ):
        self.vcs = vcs_repo
        self.llm = llm_provider
        self.rag = embedding_store
        self.analyzer = static_analyzer
        self.ast_parser = ast_parser
        self.config = config_repo
    
    def conduct_review(self, pr_id: str) -> ReviewResult:
        """
        Główny proces review:
        1. Pobranie PR i konfiguracji projektu
        2. Sprawdzenie rozmiaru PR i ewentualne chunkowanie
        3. Budowanie kontekstu (RAG retrieval + standardy z konfigu)
        4. Analiza statyczna (walidacja funkcjonalna)
        5. Generacja komentarzy LLM (z chunkowaniem dla dużych PR)
        6. Filtracja i ranking komentarzy
        7. Identyfikacja critical issues (human-in-the-loop)
        """
        # Krok 1: Fetch PR
        pr = self.vcs.fetch_pull_request(pr_id)
        config = self.config.get_config(pr.repository)
        
        # Krok 2: Chunkowanie dla dużych PR
        if pr.should_chunk(max_lines_per_chunk=config.max_chunk_size):
            logger.info(f"PR {pr_id} is large ({pr.total_changes} lines), chunking enabled")
            return self._conduct_chunked_review(pr, config)
        
        # Krok 3: Wybór konfiguracji LLM i RAG na podstawie zmian
        changed_files = pr.get_changed_files()
        llm_config = self._select_llm_config(changed_files, config)
        rag_config = self._select_rag_config(changed_files, config)
        
        # Krok 4: Budowanie kontekstu bazowego (RAG + rules + docs)
        base_context = self._build_context(pr, config, rag_config)
        
        # Krok 5: Fetch raw CI results
        raw_ci_results = self._fetch_ci_results(pr, config)
        
        # Krok 6: Parse CI results przez pomocniczy LLM (filtering + structuring)
        parsed_ci_issues = self._parse_ci_results_with_llm(
            raw_results=raw_ci_results,
            diff=pr.diff,
            changed_files=[str(f) for f in changed_files]
        )
        
        # Krok 7: Enrich context z parsed CI issues
        context = self._enrich_context(base_context, parsed_ci_issues)
        
        # Krok 8: LLM generation (z kontekstem zawierającym parsed CI issues)
        llm_comments = self.llm.generate_review(
            diff=pr.to_diff_string(),
            context=context,  # Zawiera parsed_ci_issues (clean, filtered)
            model_config=llm_config
        )
        
        # Krok 9: Rank komentarzy (LLM już wziął pod uwagę CI issues)
        ranked_comments = self._rank_by_severity(llm_comments)
        
        # Krok 10: Human-in-the-loop check
        critical_comments = [c for c in ranked_comments if c.severity == Severity.CRITICAL]
        requires_human = len(critical_comments) > config.human_threshold
        
        return ReviewResult(
            comments=ranked_comments,
            requires_human_review=requires_human,
            metadata={
                "context_size": len(context.to_prompt_context(changed_files)),
                "cost": self.llm.last_cost,
                "chunked": False,
                "llm_model": llm_config.model,
                "rag_top_k": rag_config.top_k,
                "ci_issues_parsed": len(parsed_ci_issues)
            }
        )
    
    def _enrich_context(self, base_context: CodeContext, parsed_ci_issues: List[ParsedCIIssue]) -> CodeContext:
        """Dodaje parsed CI issues do bazowego kontekstu."""
        return CodeContext(
            documentation_chunks=base_context.documentation_chunks,
            historical_reviews=base_context.historical_reviews,
            general_rules=base_context.general_rules,
            file_pattern_rules=base_context.file_pattern_rules,
            architectural_docs=base_context.architectural_docs,
            parsed_ci_issues=parsed_ci_issues,  # Dodane sparsowane issues
            extracted_functions=base_context.extracted_functions,  # Zachowane z base
            similar_prs=base_context.similar_prs
        )
    
    def _extract_functions_from_diff(self, pr: PullRequest) -> List[FunctionNode]:
        """
        Ekstrakcja funkcji ze zmienionych plików (Tree-sitter AST).
        Context enhancement - LLM widzi pełne funkcje, nie tylko diff fragments.
        
        Literatura:
        - Meng2025RARe: RAG retrieval top-1 to top-5 z FAISS
        - Pornprasit2024FineTuningPromptingCR: Tree-sitter ekstrahuje funkcje
        - Ren2025HydraReviewer: Call graph + izolacja funkcji
        """
        extracted = []
        
        for hunk in pr.diff_hunks:
            try:
                # Fetch full file content (not just diff)
                full_code = self.vcs.fetch_file(
                    pr.repository,
                    str(hunk.file_path),
                    branch=pr.source_branch
                )
                
                # Extract changed functions
                language = hunk._detect_language()
                if language != Language.UNKNOWN:
                    functions = self.ast_parser.extract_changed_functions(
                        hunk, full_code, language
                    )
                    extracted.extend(functions)
            
            except (FileNotFoundError, UnsupportedLanguageException) as e:
                logger.debug(f"Skipping AST parsing for {hunk.file_path}: {e}")
                continue
        
        # Limit to prevent context overflow (top-5 most changed)
        return sorted(extracted, key=lambda f: f.end_line - f.start_line, reverse=True)[:5]
    
    def _conduct_chunked_review(self, pr: PullRequest, config: ProjectConfig) -> ReviewResult:
        """
        Proces review dla dużych PR z chunkowaniem.
        Każdy chunk jest przetwarzany osobno, wyniki agregowane.
        """
        chunks = pr.create_chunks(chunk_size=config.max_chunk_size)
        logger.info(f"Created {len(chunks)} chunks for PR {pr.id}")
        
        all_comments = []
        total_cost = 0.0
        
        # Wybór konfiguracji LLM i RAG na podstawie zmian
        changed_files = pr.get_changed_files()
        llm_config = self._select_llm_config(changed_files, config)
        rag_config = self._select_rag_config(changed_files, config)
        
        # Kontekst bazowy (bez CI)
        base_context = self._build_context(pr, config, rag_config)
        
        # Fetch i parse CI results raz dla całego PR
        raw_ci_results = self._fetch_ci_results(pr, config)
        all_parsed_ci_issues = self._parse_ci_results_with_llm(
            raw_results=raw_ci_results,
            diff=pr.diff,
            changed_files=[str(f) for f in changed_files]
        )
        
        for i, chunk in enumerate(chunks):
            logger.info(f"Processing chunk {i+1}/{len(chunks)} for PR {pr.id}")
            
            # Filtruj parsed CI issues do plików w tym chunku
            chunk_files = {str(hunk.file_path) for hunk in chunk.diff_hunks}
            chunk_ci_issues = [
                issue for issue in all_parsed_ci_issues
                if issue.file_path in chunk_files
            ]
            
            # Enrich context dla chunka (z przefiltrowanymi CI issues)
            chunk_context = self._enrich_context(base_context, chunk_ci_issues)
            
            # LLM generation per chunk (kontekst zawiera CI issues dla chunków)
            chunk_llm_comments = self.llm.generate_review(
                diff=chunk.to_diff_string(),
                context=chunk_context,  # CI issues jako źródło kontekstu
                model_config=llm_config
            )
            
            all_comments.extend(chunk_llm_comments)
            total_cost += self.llm.last_cost
        
        # Deduplikacja komentarzy (ten sam plik/linia może być w wielu chunkach)
        unique_comments = self._deduplicate_comments(all_comments)
        ranked_comments = self._rank_by_severity(unique_comments)
        
        # Human-in-the-loop check
        critical_comments = [c for c in ranked_comments if c.severity == Severity.CRITICAL]
        requires_human = len(critical_comments) > config.human_threshold
        
        return ReviewResult(
            comments=ranked_comments,
            requires_human_review=requires_human,
            metadata={
                "context_size": len(base_context.to_prompt_context(changed_files)),
                "cost": total_cost,
                "chunked": True,
                "chunk_count": len(chunks),
                "llm_model": llm_config.model,
                "rag_top_k": rag_config.top_k,
                "ci_issues_parsed": len(all_parsed_ci_issues)
            }
        )
    
    def _deduplicate_comments(self, comments: List[ReviewComment]) -> List[ReviewComment]:
        """
        Deduplikacja komentarzy po (file_path, line_number).
        W przypadku duplikatów, priorytet ma komentarz z wyższą severity.
        """
        seen = {}
        for comment in comments:
            key = (str(comment.file_path), comment.line_number)
            if key not in seen or comment.severity.value > seen[key].severity.value:
                seen[key] = comment
        return list(seen.values())
    
    def _build_context(self, pr: PullRequest, config: ProjectConfig, rag_config: RAGConfig) -> CodeContext:
        """
        Budowanie kontekstu bazowego (RAG + rules + docs).
        NIE zawiera CI results - te są dodawane osobno przez _enrich_context().
        Zasady jako tekst LLM-friendly z konfiguracji.
        Automatyczne dołączanie .md files z repo (ARCHITECTURE.md, ADR/*.md).
        Używa rag_config (global lub per-file override).
        """
        query = pr.title + " " + pr.description
        changed_files = pr.get_changed_files()
        
        # Retrieval dokumentacji (RAG similarity search) - użyj rag_config.top_k
        if rag_config.enabled:
            rag_docs = self.rag.retrieve_top_k(query, k=rag_config.top_k)
        else:
            rag_docs = []
        
        # Retrieval historycznych review
        historical = self.vcs.fetch_historical_reviews(pr.repository, limit=50)
        similar_reviews = self._filter_similar(query, historical, top_k=5)
        
        # Fetch architectural docs z repo (.md files) - użyj rag_config.architectural_docs
        architectural_docs = self._fetch_architectural_docs(
            pr.repository, 
            rag_config.architectural_docs  # Per-file override lub global
        )
        
        # Ekstrakcja funkcji z diff (Tree-sitter AST) - augmentacja kontekstu
        extracted_functions = self._extract_functions_from_diff(pr)
        
        return CodeContext(
            documentation_chunks=[d.content for d in rag_docs],
            historical_reviews=similar_reviews,
            # Ogólne zestawy zasad (text-based, LLM-friendly)
            general_rules=config.general_rule_sets,
            # Zasady per file pattern (dopasowane podczas to_prompt_context)
            file_pattern_rules=config.file_pattern_rules,
            # Dokumenty architektoniczne z repo
            architectural_docs=architectural_docs,
            # CI issues dodawane później przez _enrich_context()
            parsed_ci_issues=[],
            # Funkcje wyekstrahowane Tree-sitter (context enhancement)
            extracted_functions=extracted_functions,
            similar_prs=[]
        )
    
    def _fetch_architectural_docs(self, repository: str, architectural_doc_paths: List[str]) -> List[ArchitecturalDocument]:
        """
        Pobiera .md files z repo wskazane w konfiguracji.
        Np. ARCHITECTURE.md, CODING_STANDARDS.md, docs/ADR/*.md
        Używa architectural_doc_paths (global lub per-file override).
        """
        docs = []
        for doc_path in architectural_doc_paths:
            try:
                # Obsługa glob patterns (docs/ADR/*.md)
                if "*" in doc_path:
                    matching_files = self.vcs.list_files(repository, pattern=doc_path)
                    for file_path in matching_files:
                        content = self.vcs.fetch_file(repository, file_path)
                        docs.append(ArchitecturalDocument(
                            filename=file_path,
                            content=content,
                            last_modified=datetime.now()
                        ))
                else:
                    # Single file
                    content = self.vcs.fetch_file(repository, doc_path)
                    docs.append(ArchitecturalDocument(
                        filename=doc_path,
                        content=content,
                        last_modified=datetime.now()
                    ))
            except FileNotFoundError:
                logger.warning(f"Architectural doc not found: {doc_path} in {repository}")
                continue
        
        logger.info(f"Fetched {len(docs)} architectural documents from {repository}")
        return docs
    
    def _select_llm_config(self, changed_files: List[FilePath], config: ProjectConfig) -> LLMConfig:
        """
        Wybiera odpowiedni LLM config na podstawie zmienionych plików.
        Jeśli jakikolwiek file pattern ma llm_config override, używa go.
        Priority: najwyższy priorytet ma pierwszaństwo.
        """
        matched_patterns = []
        
        for file_path in changed_files:
            for pattern_rule in config.file_pattern_rules:
                if pattern_rule.llm_config and fnmatch.fnmatch(str(file_path), pattern_rule.pattern):
                    matched_patterns.append((pattern_rule.priority, pattern_rule.llm_config))
        
        if matched_patterns:
            # Sortuj po priorytecie (malejąco) i wybierz pierwszy
            matched_patterns.sort(key=lambda x: x[0], reverse=True)
            selected = matched_patterns[0][1]
            logger.info(f"Using LLM override: {selected.model} (priority {matched_patterns[0][0]})")
            return selected
        
        # Fallback do global LLM config
        return LLMConfig(
            provider=config.llm_provider,
            model=config.llm_model,
            temperature=config.llm_temperature,
            max_tokens=config.llm_max_tokens
        )
    
    def _select_rag_config(self, changed_files: List[FilePath], config: ProjectConfig) -> RAGConfig:
        """
        Wybiera odpowiedni RAG config na podstawie zmienionych plików.
        Jeśli jakikolwiek file pattern ma rag_config override, używa go.
        Priority: najwyższy priorytet ma pierwszaństwo.
        """
        matched_patterns = []
        
        for file_path in changed_files:
            for pattern_rule in config.file_pattern_rules:
                if pattern_rule.rag_config and fnmatch.fnmatch(str(file_path), pattern_rule.pattern):
                    matched_patterns.append((pattern_rule.priority, pattern_rule.rag_config))
        
        if matched_patterns:
            # Sortuj po priorytecie (malejąco) i wybierz pierwszy
            matched_patterns.sort(key=lambda x: x[0], reverse=True)
            selected = matched_patterns[0][1]
            logger.info(f"Using RAG override: top_k={selected.top_k}, docs={len(selected.architectural_docs)} (priority {matched_patterns[0][0]})")
            return selected
        
        # Fallback do global RAG config
        return RAGConfig(
            enabled=config.rag_enabled,
            top_k=config.rag_top_k,
            documentation_paths=config.documentation_paths,
            architectural_docs=config.architectural_doc_paths
        )
    
    def _fetch_ci_results(
        self, pr: PullRequest, config: ProjectConfig
    ) -> List[CIToolResult]:
        """
        Pobiera luźno zebrane wyniki z CI/CD jako źródło kontekstu dla LLM.
        
        Flow:
        1. Sprawdź czy CI zakończył działanie
        2. Jeśli nie - wait with timeout lub skip
        3. Jeśli tak - fetch results z GitHub Checks / GitLab CI
        4. Zwróć CIToolResult[] - różne formaty per tool
        
        Wyniki są w różnych formatach:
        - JSON structured (jeśli narzędzie wspiera)
        - Plain text output
        - Logi z failed jobs
        
        LLM dostaje te wyniki w raw formie i sam interpretuje:
        - Potwierdza issues
        - Dodaje kontekst i wyjaśnienia
        - Sugeruje konkretne fixy
        - Wykrywa false positives
        - Znajduje powiązane problemy
        """
        if not config.static_analysis_enabled:
            return []
        
        # Krok 1: Sprawdź status CI
        if not self.analyzer.is_ci_completed(pr):
            # Wait with timeout
            timeout = config.static_analysis_timeout  # np. 300s
            logger.info(f"Waiting for CI to complete (timeout: {timeout}s)")
            
            waited = 0
            while not self.analyzer.is_ci_completed(pr) and waited < timeout:
                time.sleep(10)
                waited += 10
            
            if not self.analyzer.is_ci_completed(pr):
                logger.warning(f"CI timeout after {timeout}s, proceeding without CI results")
                return []
        
        # Krok 2: Fetch results z CI/CD (różne formaty)
        logger.info(f"Fetching CI results for PR {pr.id}")
        results = self.analyzer.fetch_ci_results(pr)
        
        logger.info(
            f"Fetched CI results from {len(results)} tools: {[r.tool_name for r in results]} - "
            f"will be parsed by LLM to extract relevant issues"
        )
        return results
    
    def _parse_ci_results_with_llm(
        self,
        raw_results: List[CIToolResult],
        diff: PullRequestDiff,
        changed_files: List[str]
    ) -> List[ParsedCIIssue]:
        """
        Krok pośredni: LLM parsuje raw CI outputs i wyodrębnia tylko relevantne issues.
        
        Flow:
        1. Dla każdego CIToolResult (Ruff, mypy, ESLint) - raw output w różnych formatach
        2. LLM prompt: "Parse this CI output, extract issues for these files: [...]"
        3. LLM zwraca structured list: [{file, line, severity, code, message, is_in_diff}]
        4. Filtrowanie: tylko issues w changed_files
        5. Zwraca List[ParsedCIIssue]
        
        Zalety:
        - LLM radzi sobie z dowolnym formatem (JSON, text, logs)
        - Automatyczne filtrowanie do changed files/lines
        - Mniejszy prompt dla głównego review (tylko relevant issues)
        - LLM może już dodać wstępne suggestions
        """
        if not raw_results:
            return []
        
        logger.info(f"Parsing {len(raw_results)} CI tool outputs with LLM...")
        
        # Prompt dla LLM parsing - structured output
        parsing_prompt = self._build_ci_parsing_prompt(
            raw_results=raw_results,
            changed_files=changed_files,
            diff=diff
        )
        
        # Wywołaj LLM z promptem do parsowania (tańszy/szybszy model)
        # np. gpt-4o-mini lub claude-3-haiku
        parsed_response = self.llm.parse_ci_output(
            prompt=parsing_prompt,
            response_format="json"  # Structured output
        )
        
        # Parse JSON response → List[ParsedCIIssue]
        parsed_issues = self._deserialize_parsed_issues(parsed_response)
        
        # Filtruj tylko issues w changed files
        relevant_issues = [
            issue for issue in parsed_issues
            if issue.file_path in changed_files
        ]
        
        logger.info(
            f"Parsed {len(parsed_issues)} total issues, "
            f"{len(relevant_issues)} relevant for changed files"
        )
        
        return relevant_issues
    
    def _build_ci_parsing_prompt(
        self,
        raw_results: List[CIToolResult],
        changed_files: List[str],
        diff: PullRequestDiff
    ) -> str:
        """
        Buduje prompt dla LLM do parsowania CI outputs.
        
        Prompt zawiera:
        - Raw outputs z każdego narzędzia
        - Lista changed files
        - Changed line ranges (z diff)
        - Zadanie: wyodrębnij issues w JSON format
        """
        prompt_parts = []
        prompt_parts.append("# Task: Parse CI Tool Outputs\n")
        prompt_parts.append(
            "Parse the following CI tool outputs and extract all issues. "
            "Focus on issues in the changed files listed below.\n"
        )
        
        # Changed files + line ranges
        prompt_parts.append("\n## Changed Files and Lines:\n```")
        for file in changed_files:
            # Get changed line ranges from diff
            line_ranges = diff.get_changed_line_ranges(file)
            if line_ranges:
                ranges_str = ", ".join([f"{r[0]}-{r[1]}" for r in line_ranges])
                prompt_parts.append(f"{file}: lines {ranges_str}")
            else:
                prompt_parts.append(f"{file}: all lines (new file or fully changed)")
        prompt_parts.append("```\n")
        
        # Raw CI outputs
        prompt_parts.append("\n## CI Tool Outputs:\n")
        for result in raw_results:
            prompt_parts.append(f"\n### Tool: {result.tool_name} ({result.conclusion})\n```")
            # Truncate very long outputs
            output = result.raw_output[:3000]
            if len(result.raw_output) > 3000:
                output += "\n... (truncated)"
            prompt_parts.append(output)
            prompt_parts.append("```\n")
        
        # Output format specification
        prompt_parts.append("\n## Required Output Format (JSON):\n```json")
        prompt_parts.append('''{
  "issues": [
    {
      "tool_name": "Ruff",
      "file_path": "src/main.py",
      "line_number": 42,
      "severity": "error",
      "issue_code": "F401",
      "message": "Unused import: typing.Optional",
      "suggestion": "Remove the unused import",
      "is_in_diff": true
    }
  ]
}''')
        prompt_parts.append("```\n")
        
        prompt_parts.append(
            "\nInstructions:\n"
            "- Extract all issues from each tool output\n"
            "- Parse different formats (JSON, text, logs) accordingly\n"
            "- For each issue, determine if it's in changed lines (is_in_diff: true/false)\n"
            "- If line number is not available, set to null\n"
            "- Add brief suggestion if obvious from the error message\n"
            "- severity: 'error', 'warning', or 'info'\n"
        )
        
        return "".join(prompt_parts)
    
    def _deserialize_parsed_issues(self, json_response: str) -> List[ParsedCIIssue]:
        """Deserializuje JSON response z LLM → List[ParsedCIIssue]."""
        import json
        
        try:
            data = json.loads(json_response)
            issues = []
            
            for item in data.get("issues", []):
                issues.append(ParsedCIIssue(
                    tool_name=item["tool_name"],
                    file_path=item["file_path"],
                    line_number=item.get("line_number"),
                    severity=item["severity"],
                    issue_code=item.get("issue_code"),
                    message=item["message"],
                    suggestion=item.get("suggestion"),
                    is_in_diff=item.get("is_in_diff", False)
                ))
            
            return issues
        except Exception as e:
            logger.error(f"Failed to parse LLM CI parsing response: {e}")
            return []
```

**ContextBuilder**
```python
class ContextBuilder:
    """Serwis domenowy do budowania kontekstu RAG."""
    
    def build_from_repository(self, repo: str, config: ProjectConfig) -> None:
        """
        Indeksowanie repozytorium do RAG (similarity search):
        - dokumentacja (README, docs/)
        - historyczne PR i komentarze
        
        NIE indeksuje architectural_docs - te są dołączane zawsze (full content).
        """
        # Index documentation paths
        for doc_path in config.documentation_paths:
            self._index_path(repo, doc_path)
        
        # Index historical reviews
        self._index_historical_reviews(repo)
    
    def extract_rules_from_config(self, config: ProjectConfig) -> Dict[str, Any]:
        """
        Wyciąga zasady z konfiguracji projektu (.acr-config.yml).
        Zasady jako tekst LLM-friendly (nie sztywne struktury).
        
        Returns:
            Dict zawierający:
            - general_rule_sets: List[RuleSet] - ogólne zasady
            - file_pattern_rules: List[FilePatternRule] - zasady per glob pattern
            - architectural_doc_paths: List[str] - ścieżki do .md files
        """
        return {
            "general_rule_sets": config.general_rule_sets,
            "file_pattern_rules": config.file_pattern_rules,
            "architectural_doc_paths": config.architectural_doc_paths
        }
    
    def _index_path(self, repo: str, path: str) -> None:
        """Indeksuje pliki z danej ścieżki do RAG (chunking + embeddings)."""
        # Implementation: fetch files, chunk, embed, store in FAISS
        pass
    
    def _index_historical_reviews(self, repo: str) -> None:
        """Indeksuje historyczne komentarze review do RAG."""
        # Implementation: fetch reviews, embed, store
        pass
```

---

## Warstwa Application (Use Cases)

### Use Case: ProcessPullRequest

```python
class ProcessPullRequestUseCase:
    """
    Use case: Przetwarzanie PR/MR od początku do końca.
    Wywołany przez webhook lub CLI.
    """
    
    def __init__(self, review_orchestrator: ReviewOrchestrator):
        self.orchestrator = review_orchestrator
    
    def execute(self, request: PRReviewRequest) -> ReviewResult:
        """
        1. Walidacja requestu
        2. Orkiestracja review (ReviewOrchestrator)
        3. Publikacja wyników
        4. Logowanie metryk
        """
        # Validations
        if not self._is_valid_request(request):
            raise InvalidRequestException()
        
        # Orchestrate review
        result = self.orchestrator.conduct_review(request.pr_id)
        
        # Publish back to VCS
        self.orchestrator.vcs.publish_comments(request.pr_id, result.comments)
        
        # Log metrics (BLEU, cost, latency)
        self._log_metrics(result)
        
        return result
```

### Use Case: RetrieveContext (RAG)

```python
class RetrieveContextUseCase:
    """Use case: RAG retrieval kontekstu dla PR."""
    
    def __init__(self, embedding_store: EmbeddingStore):
        self.store = embedding_store
    
    def execute(self, query: str, top_k: int) -> List[Document]:
        """
        Retrieval top-k dokumentów z bazy wektorowej.
        Może być wywołane niezależnie do testowania RAG.
        """
        return self.store.retrieve_top_k(query, k=top_k)
```

---

## Warstwa Infrastructure (Adaptery)

### Adapter VCS: GitHubAdapter

```python
class GitHubAdapter(VCSRepository):
    """Implementacja portu VCSRepository dla GitHub."""
    
    def __init__(self, token: str, base_url: str = "https://api.github.com"):
        self.token = token
        self.base_url = base_url
        self.client = httpx.Client(headers={"Authorization": f"Bearer {token}"})
    
    def fetch_pull_request(self, pr_id: str) -> PullRequest:
        """GET /repos/{owner}/{repo}/pulls/{pull_number}"""
        response = self.client.get(f"{self.base_url}/repos/{self._parse_repo(pr_id)}/pulls/{self._parse_number(pr_id)}")
        response.raise_for_status()
        data = response.json()
        
        return PullRequest(
            id=pr_id,
            repository=data["base"]["repo"]["full_name"],
            source_branch=data["head"]["ref"],
            target_branch=data["base"]["ref"],
            author=data["user"]["login"],
            diff_hunks=self.fetch_diff(pr_id),
            metadata=data
        )
    
    def fetch_diff(self, pr_id: str) -> List[DiffHunk]:
        """
        GET /repos/{owner}/{repo}/pulls/{pull_number}/files
        Parsowanie unified diff format.
        
        UWAGA: GitHub API paginuje wyniki (max 30/100 plików na stronę).
        Dla dużych PR konieczne jest iterowanie przez strony.
        """
        all_files = []
        page = 1
        per_page = 100  # GitHub max
        
        while True:
            response = self.client.get(
                f"{self.base_url}/repos/{self._parse_repo(pr_id)}/pulls/{self._parse_number(pr_id)}/files",
                params={"page": page, "per_page": per_page}
            )
            response.raise_for_status()
            files = response.json()
            
            if not files:
                break  # Brak więcej stron
            
            all_files.extend(files)
            
            # Sprawdzenie czy są kolejne strony (Link header)
            if "Link" not in response.headers or "rel=\"next\"" not in response.headers["Link"]:
                break
            
            page += 1
        
        logger.info(f"Fetched {len(all_files)} files from PR {pr_id} (across {page} pages)")
        return [self._parse_diff_hunk(f) for f in all_files]
    
    def publish_comments(self, pr_id: str, comments: List[ReviewComment]) -> None:
        """
        POST /repos/{owner}/{repo}/pulls/{pull_number}/comments
        Publikacja jako inline comments w PR.
        """
        for comment in comments:
            payload = {
                "path": str(comment.file_path),
                "line": comment.line_number,
                "body": self._format_comment(comment),
                "side": "RIGHT"
            }
            self.client.post(
                f"{self.base_url}/repos/{self._parse_repo(pr_id)}/pulls/{self._parse_number(pr_id)}/comments",
                json=payload
            )
    
    def _format_comment(self, comment: ReviewComment) -> str:
        """
        Formatowanie komentarza z severity i source:
        
        ⚠️ **WARNING** (Static Analysis: Ruff)
        Unused import: `typing.Optional`
        
        **Suggested fix:**
        ```python
        # Remove line 5
        ```
        """
        emoji = {"INFO": "ℹ️", "WARNING": "⚠️", "ERROR": "❌", "CRITICAL": "🚨"}[comment.severity.name]
        msg = f"{emoji} **{comment.severity.name}** ({comment.source.value})\n{comment.message}"
        
        if comment.suggested_fix:
            msg += f"\n\n**Suggested fix:**\n```\n{comment.suggested_fix}\n```"
        
        return msg
```

### Adapter CI: GitHubChecksAdapter

```python
class GitHubChecksAdapter(StaticAnalyzer):
    """
    Implementacja portu StaticAnalyzer dla GitHub Checks API.
    Pobiera wyniki narzędzi CI (Ruff, mypy, ESLint) z GitHub Checks.
    """
    
    def __init__(self, token: str, base_url: str = "https://api.github.com"):
        self.token = token
        self.base_url = base_url
        self.client = self._create_client()
    
    def fetch_ci_results(self, pr: PullRequest) -> List[CIToolResult]:
        """
        Pobiera luźno zebrane wyniki z GitHub Checks API.
        GET /repos/{owner}/{repo}/commits/{ref}/check-runs
        
        Różne narzędzia = różne formaty (JSON annotations, summary text).
        """
        owner_repo = self._parse_repo(pr.repository)
        check_runs_response = self.client.get(
            f"{self.base_url}/repos/{owner_repo}/commits/{pr.head_sha}/check-runs",
            headers={"Accept": "application/vnd.github.v3+json"}
        )
        
        check_runs = check_runs_response.json()["check_runs"]
        results = []
        
        for check_run in check_runs:
            tool_name = check_run["name"]  # "Ruff", "mypy", "ESLint", etc.
            status = check_run["status"]  # "completed", "in_progress"
            conclusion = check_run.get("conclusion")  # "success", "failure", "neutral"
            
            if status != "completed":
                continue  # Skip in-progress checks
            
            # Fetch annotations (structured issues)
            annotations_url = check_run["url"] + "/annotations"
            annotations_resp = self.client.get(annotations_url)
            annotations = annotations_resp.json()
            
            # Fetch output summary (może być plain text)
            output_summary = check_run.get("output", {}).get("summary", "")
            
            # Combine annotations + summary jako raw_output
            raw_output = self._format_raw_output(annotations, output_summary)
            
            # Extract mentioned files
            files_mentioned = set()
            for annotation in annotations:
                if "path" in annotation:
                    files_mentioned.add(annotation["path"])
            
            results.append(CIToolResult(
                tool_name=tool_name,
                status=conclusion,
                raw_output=raw_output,
                files_mentioned=files_mentioned,
                conclusion=conclusion
            ))
        
        return results
    
    def is_ci_completed(self, pr: PullRequest) -> bool:
        """Sprawdza czy CI zakończył działanie."""
        owner_repo = self._parse_repo(pr.repository)
        check_runs_response = self.client.get(
            f"{self.base_url}/repos/{owner_repo}/commits/{pr.head_sha}/check-runs"
        )
        
        check_runs = check_runs_response.json()["check_runs"]
        return all(run["status"] == "completed" for run in check_runs)
    
    def _format_raw_output(self, annotations: List[Dict], summary: str) -> str:
        """
        Formatuje annotations + summary do raw text output.
        Helper LLM będzie to parsował.
        """
        lines = []
        
        # Annotations (structured)
        if annotations:
            lines.append("=== Annotations ===")
            for ann in annotations:
                lines.append(
                    f"{ann.get('path', 'unknown')}:{ann.get('start_line', '?')}: "
                    f"[{ann.get('annotation_level', 'notice').upper()}] "
                    f"{ann.get('message', '')}"
                )
        
        # Summary (może być plain text z STDOUT narzędzia)
        if summary:
            lines.append("\n=== Summary ===")
            lines.append(summary)
        
        return "\n".join(lines)
    
    def _parse_repo(self, repository: str) -> str:
        """Parsuje 'owner/repo' z repository string."""
        # repository może być "github.com/owner/repo" lub "owner/repo"
        parts = repository.split("/")
        return f"{parts[-2]}/{parts[-1]}"
    
    def _create_client(self):
        """Tworzy HTTP client z autentykacją."""
        import requests
        session = requests.Session()
        session.headers.update({
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json"
        })
        return session
```

### Adapter CI: GitLabCIAdapter

```python
class GitLabCIAdapter(StaticAnalyzer):
    """
    Implementacja portu StaticAnalyzer dla GitLab CI.
    Pobiera wyniki z GitLab CI artifacts i job logs.
    """
    
    def __init__(self, token: str, base_url: str = "https://gitlab.com/api/v4"):
        self.token = token
        self.base_url = base_url
        self.client = self._create_client()
    
    def fetch_ci_results(self, pr: PullRequest) -> List[CIToolResult]:
        """
        Pobiera wyniki z GitLab CI artifacts/logs.
        GET /projects/{id}/merge_requests/{iid}/pipelines
        GET /projects/{id}/pipelines/{pipeline_id}/jobs
        GET /projects/{id}/jobs/{job_id}/artifacts
        """
        project_id = self._parse_project_id(pr.repository)
        mr_iid = self._parse_mr_iid(pr.id)
        
        # Fetch latest pipeline for MR
        pipelines_resp = self.client.get(
            f"{self.base_url}/projects/{project_id}/merge_requests/{mr_iid}/pipelines"
        )
        pipelines = pipelines_resp.json()
        
        if not pipelines:
            return []
        
        latest_pipeline = pipelines[0]
        pipeline_id = latest_pipeline["id"]
        
        # Fetch jobs for pipeline
        jobs_resp = self.client.get(
            f"{self.base_url}/projects/{project_id}/pipelines/{pipeline_id}/jobs"
        )
        jobs = jobs_resp.json()
        
        results = []
        
        for job in jobs:
            tool_name = job["name"]  # "ruff", "mypy", "eslint"
            status = job["status"]  # "success", "failed", "canceled"
            
            if status not in ["success", "failed"]:
                continue
            
            # Try to fetch artifacts (może zawierać JSON report)
            try:
                artifacts_resp = self.client.get(
                    f"{self.base_url}/projects/{project_id}/jobs/{job['id']}/artifacts",
                    stream=True
                )
                raw_artifacts = artifacts_resp.text
            except:
                raw_artifacts = ""
            
            # Fetch job log (STDOUT narzędzia)
            try:
                log_resp = self.client.get(
                    f"{self.base_url}/projects/{project_id}/jobs/{job['id']}/trace"
                )
                job_log = log_resp.text
            except:
                job_log = ""
            
            # Combine artifacts + log
            raw_output = f"=== Artifacts ===\n{raw_artifacts}\n\n=== Job Log ===\n{job_log}"
            
            # Extract files (best-effort z artifacts/logs)
            files_mentioned = self._extract_files_from_output(raw_output)
            
            results.append(CIToolResult(
                tool_name=tool_name,
                status=status,
                raw_output=raw_output,
                files_mentioned=files_mentioned,
                conclusion=status
            ))
        
        return results
    
    def is_ci_completed(self, pr: PullRequest) -> bool:
        """Sprawdza czy CI zakończył działanie."""
        project_id = self._parse_project_id(pr.repository)
        mr_iid = self._parse_mr_iid(pr.id)
        
        pipelines_resp = self.client.get(
            f"{self.base_url}/projects/{project_id}/merge_requests/{mr_iid}/pipelines"
        )
        pipelines = pipelines_resp.json()
        
        if not pipelines:
            return False
        
        latest_pipeline = pipelines[0]
        return latest_pipeline["status"] in ["success", "failed", "canceled"]
    
    def _extract_files_from_output(self, output: str) -> Set[str]:
        """Best-effort extraction plików z raw output (regex)."""
        import re
        # Pattern: path/to/file.py:123
        pattern = r'([a-zA-Z0-9_/.-]+\.(py|js|ts|go|java|rb)):\d+'
        matches = re.findall(pattern, output)
        return set([m[0] for m in matches])
    
    def _parse_project_id(self, repository: str) -> str:
        """Parsuje project ID z repository URL."""
        # repository: "gitlab.com/group/project" -> URL-encode "group/project"
        parts = repository.split("/")
        project_path = "/".join(parts[-2:])
        return urllib.parse.quote(project_path, safe='')
    
    def _parse_mr_iid(self, pr_id: str) -> str:
        """Parsuje MR IID z pr_id."""
        # pr_id: "gitlab/group/project/merge_requests/123" -> "123"
        return pr_id.split("/")[-1]
    
    def _create_client(self):
        """Tworzy HTTP client z autentykacją."""
        import requests
        session = requests.Session()
        session.headers.update({
            "PRIVATE-TOKEN": self.token
        })
        return session
```

### LLM Provider Factory (Open/Closed Principle)

```python
class LLMProviderFactory:
    """
    Factory dla tworzenia LLM providerów.
    Open/Closed Principle: dodawanie nowych providerów bez modyfikacji istniejącego kodu.
    
    Użycie:
    - Dodaj nowy provider: LLMProviderFactory.register("gemini", GeminiAdapter)
    - Twórz instancję: factory.create("gemini", api_key=...)
    """
    _providers: Dict[str, Type[LLMProvider]] = {}
    
    @classmethod
    def register(cls, provider_name: str, provider_class: Type[LLMProvider]) -> None:
        """Rejestruje nowy LLM provider."""
        cls._providers[provider_name] = provider_class
        logger.info(f"Registered LLM provider: {provider_name}")
    
    @classmethod
    def create(cls, provider_name: str, **kwargs) -> LLMProvider:
        """
        Tworzy instancję LLM providera.
        
        Args:
            provider_name: Nazwa providera ("openai", "anthropic", "gemini", etc.)
            **kwargs: Parametry dla konstruktora providera
        
        Raises:
            ValueError: Jeśli provider nie jest zarejestrowany
        """
        if provider_name not in cls._providers:
            available = ", ".join(cls._providers.keys())
            raise ValueError(
                f"Unknown LLM provider: {provider_name}. "
                f"Available providers: {available}"
            )
        
        provider_class = cls._providers[provider_name]
        return provider_class(**kwargs)
    
    @classmethod
    def list_providers(cls) -> List[str]:
        """Zwraca listę zarejestrowanych providerów."""
        return list(cls._providers.keys())

# Auto-registration providerów (wywoływane podczas importu modułów)
def register_builtin_providers():
    """Rejestruje wbudowane providery."""
    from adapters.llm.openai_adapter import OpenAIAdapter
    from adapters.llm.anthropic_adapter import AnthropicAdapter
    
    LLMProviderFactory.register("openai", OpenAIAdapter)
    LLMProviderFactory.register("anthropic", AnthropicAdapter)

# Call on module import
register_builtin_providers()
```

**Przykład dodawania nowego providera (Google Gemini)**:
```python
# adapters/llm/gemini_adapter.py

class GeminiAdapter(LLMProvider):
    """Implementacja dla Google Gemini."""
    
    def __init__(self, api_key: str, model: str = "gemini-1.5-pro"):
        self.api_key = api_key
        self.model = model
        self.client = genai.Client(api_key=api_key)
    
    def generate_review(self, diff: str, context: CodeContext, config: ModelConfig) -> List[ReviewComment]:
        # Implementation...
        pass
    
    def parse_ci_output(self, prompt: str, response_format: str = "json") -> str:
        # Implementation...
        pass
    
    def estimate_cost(self, input_tokens: int, output_tokens: int, model: str = None) -> float:
        # Gemini pricing
        return (input_tokens / 1000) * 0.001 + (output_tokens / 1000) * 0.002

# Rejestracja (w __init__.py lub podczas importu)
LLMProviderFactory.register("gemini", GeminiAdapter)

# Użycie w Container:
# instance = LLMProviderFactory.create("gemini", api_key=os.getenv("GEMINI_API_KEY"))
```

**Korzyści Open/Closed**:
- ✅ Dodanie Gemini = tylko nowy plik `gemini_adapter.py`
- ✅ Brak modyfikacji `OpenAIAdapter`, `Container`, `ReviewOrchestrator`
- ✅ Automatyczna rejestracja przez import
- ✅ Type safety (Type[LLMProvider])

### Adapter LLM: OpenAIAdapter

```python
class OpenAIAdapter(LLMProvider):
    """Implementacja portu LLMProvider dla OpenAI (GPT-4/4o)."""
    
    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self.api_key = api_key
        self.model = model
        self.client = openai.Client(api_key=api_key)
    
    def generate_review(
        self, 
        diff: str, 
        context: CodeContext,
        model_config: ModelConfig
    ) -> List[ReviewComment]:
        """
        Wywołanie OpenAI Chat Completions API z promptem strukturyzowanym.
        """
        prompt = self._build_prompt(diff, context, model_config)
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self._system_prompt(model_config)},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,  # Niższa temperatura dla deterministyczności
            max_tokens=2000
        )
        
        # Parsowanie odpowiedzi LLM do ReviewComment
        raw_output = response.choices[0].message.content
        comments = self._parse_llm_output(raw_output)
        
        # Logowanie kosztów
        self.last_cost = self.estimate_cost(
            response.usage.prompt_tokens,
            response.usage.completion_tokens
        )
        
        return comments
    
    def _build_prompt(self, diff: str, context: CodeContext, config: ModelConfig) -> str:
        """
        Struktura promptu:
        
        # Code Review Task
        
        ## Context
        {context.to_prompt_context()}
        
        ## Diff to Review
        ```diff
        {diff}
        ```
        
        ## Instructions
        - Focus on: {config.review_priorities}
        - Provide actionable feedback
        - Output format: JSON array of comments
        
        ## Output Schema
        [
          {
            "file": "path/to/file.py",
            "line": 42,
            "severity": "WARNING",
            "message": "...",
            "suggested_fix": "..."
          }
        ]
        """
        return f"""# Code Review Task

## Context
{context.to_prompt_context()}

## Diff to Review
```diff
{diff}
```

## Instructions
- Review priorities: {", ".join(config.review_priorities)}
- Provide specific, actionable feedback
- Focus on: correctness, security, performance, maintainability
- Output as JSON array

## Output Schema
[
  {{
    "file": "path/to/file.py",
    "line": 42,
    "severity": "INFO|WARNING|ERROR|CRITICAL",
    "message": "Clear description of the issue",
    "suggested_fix": "Optional concrete fix"
  }}
]
"""
    
    def _parse_llm_output(self, raw_output: str) -> List[ReviewComment]:
        """Parsowanie JSON z odpowiedzi LLM do obiektów ReviewComment."""
        try:
            data = json.loads(raw_output)
            return [
                ReviewComment(
                    file_path=FilePath(item["file"]),
                    line_number=item["line"],
                    severity=Severity[item["severity"]],
                    message=item["message"],
                    source=CommentSource.LLM,
                    suggested_fix=item.get("suggested_fix")
                )
                for item in data
            ]
        except (json.JSONDecodeError, KeyError) as e:
            # Fallback: parsowanie tekstowe
            logger.warning(f"Failed to parse LLM JSON output: {e}")
            return self._fallback_parse(raw_output)
    
    def parse_ci_output(self, prompt: str, response_format: str = "json") -> str:
        """
        Parsuje raw CI outputs przez pomocniczy LLM (GPT-4o-mini).
        Używa tańszego modelu dla optymalizacji kosztów.
        """
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",  # Tańszy model dla parsowania
            messages=[
                {"role": "system", "content": "You are a CI output parser. Parse tool outputs and return structured JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,  # Bardzo niska temperatura dla deterministycznego parsowania
            max_tokens=4000,
            response_format={"type": "json_object"} if response_format == "json" else None
        )
        
        # Logowanie kosztów parsowania
        self.last_parsing_cost = self.estimate_cost(
            response.usage.prompt_tokens,
            response.usage.completion_tokens,
            model="gpt-4o-mini"
        )
        
        return response.choices[0].message.content
    
    def estimate_cost(self, input_tokens: int, output_tokens: int, model: str = None) -> float:
        """
        Estymuje koszt wywołania API dla różnych modeli.
        
        Pricing (2024):
        - GPT-4o: $0.005/1K input, $0.015/1K output
        - GPT-4o-mini: $0.00015/1K input, $0.0006/1K output
        """
        model = model or self.model
        
        if "gpt-4o-mini" in model:
            input_cost = (input_tokens / 1000) * 0.00015
            output_cost = (output_tokens / 1000) * 0.0006
        elif "gpt-4o" in model:
            input_cost = (input_tokens / 1000) * 0.005
            output_cost = (output_tokens / 1000) * 0.015
        else:
            # Default GPT-4 pricing
            input_cost = (input_tokens / 1000) * 0.01
            output_cost = (output_tokens / 1000) * 0.03
        
        return input_cost + output_cost
```

### Adapter RAG: FAISSStore

```python
class FAISSStore(EmbeddingStore):
    """Implementacja portu EmbeddingStore z użyciem FAISS."""
    
    def __init__(self, embedding_service: EmbeddingService, index_path: str):
        self.embedder = embedding_service
        self.index = faiss.IndexFlatL2(self.embedder.dimension)
        self.doc_store: Dict[int, Document] = {}
        self.index_path = index_path
    
    def index_document(self, doc_id: str, text: str, metadata: Dict) -> None:
        """Indeksowanie dokumentu w FAISS."""
        embedding = self.embedder.embed(text)
        idx = len(self.doc_store)
        
        self.index.add(np.array([embedding], dtype=np.float32))
        self.doc_store[idx] = Document(
            id=doc_id,
            content=text,
            metadata=metadata,
            embedding=embedding
        )
    
    def retrieve_top_k(self, query: str, k: int) -> List[Document]:
        """Retrieval top-k dokumentów najbardziej podobnych."""
        query_embedding = self.embedder.embed(query)
        distances, indices = self.index.search(
            np.array([query_embedding], dtype=np.float32), 
            k
        )
        
        return [self.doc_store[idx] for idx in indices[0]]
    
    def clear_index(self, repository: str) -> None:
        """Usuwa dokumenty dla danego repozytorium."""
        # Filter by metadata.repository
        to_remove = [
            idx for idx, doc in self.doc_store.items() 
            if doc.metadata.get("repository") == repository
        ]
        # FAISS nie wspiera usuwania - rebuild index
        self._rebuild_index_without(to_remove)
```

### Language Strategy Pattern (Open/Closed Principle)

```python
class LanguageStrategy(ABC):
    """
    Strategia parsowania dla konkretnego języka (Tree-sitter).
    Open/Closed Principle: dodawanie nowych języków bez modyfikacji TreeSitterParser.
    """
    
    @abstractmethod
    def get_function_query(self) -> str:
        """Zwraca Tree-sitter query dla function_definition."""
    
    @abstractmethod
    def get_call_expression_query(self) -> str:
        """Zwraca Tree-sitter query dla call_expression."""
    
    @abstractmethod
    def extract_function_name(self, node) -> str:
        """Ekstrakcja nazwy funkcji z AST node."""
    
    @abstractmethod
    def get_parser_name(self) -> str:
        """Nazwa parsera Tree-sitter (np. 'python', 'javascript')."""

class PythonLanguageStrategy(LanguageStrategy):
    """Strategia dla Python."""
    
    def get_function_query(self) -> str:
        return "(function_definition) @function"
    
    def get_call_expression_query(self) -> str:
        return "(call (identifier) @call)"
    
    def extract_function_name(self, node) -> str:
        for child in node.children:
            if child.type == "identifier":
                return child.text.decode("utf8")
        return "<anonymous>"
    
    def get_parser_name(self) -> str:
        return "python"

class JavaScriptLanguageStrategy(LanguageStrategy):
    """Strategia dla JavaScript."""
    
    def get_function_query(self) -> str:
        return "(function_declaration) @function"
    
    def get_call_expression_query(self) -> str:
        return "(call_expression (identifier) @call)"
    
    def extract_function_name(self, node) -> str:
        for child in node.children:
            if child.type == "identifier":
                return child.text.decode("utf8")
        return "<anonymous>"
    
    def get_parser_name(self) -> str:
        return "javascript"

class TypeScriptLanguageStrategy(LanguageStrategy):
    """Strategia dla TypeScript."""
    
    def get_function_query(self) -> str:
        return "(function_declaration) @function"
    
    def get_call_expression_query(self) -> str:
        return "(call_expression (identifier) @call)"
    
    def extract_function_name(self, node) -> str:
        for child in node.children:
            if child.type == "identifier":
                return child.text.decode("utf8")
        return "<anonymous>"
    
    def get_parser_name(self) -> str:
        return "typescript"

class GoLanguageStrategy(LanguageStrategy):
    """Strategia dla Go."""
    
    def get_function_query(self) -> str:
        return "(function_declaration) @function"
    
    def get_call_expression_query(self) -> str:
        return "(call_expression (identifier) @call)"
    
    def extract_function_name(self, node) -> str:
        for child in node.children:
            if child.type == "identifier":
                return child.text.decode("utf8")
        return "<anonymous>"
    
    def get_parser_name(self) -> str:
        return "go"

# Registry wzorzec
class LanguageRegistry:
    """
    Rejestr strategii języków.
    Centralizuje zarządzanie supported languages.
    """
    _strategies: Dict[Language, LanguageStrategy] = {}
    
    @classmethod
    def register(cls, language: Language, strategy: LanguageStrategy) -> None:
        """Rejestruje strategię dla języka."""
        cls._strategies[language] = strategy
        logger.info(f"Registered language strategy: {language.value}")
    
    @classmethod
    def get(cls, language: Language) -> Optional[LanguageStrategy]:
        """Pobiera strategię dla języka."""
        return cls._strategies.get(language)
    
    @classmethod
    def is_supported(cls, language: Language) -> bool:
        """Sprawdza czy język jest wspierany."""
        return language in cls._strategies
    
    @classmethod
    def list_supported(cls) -> List[Language]:
        """Zwraca listę wspieranych języków."""
        return list(cls._strategies.keys())

# Auto-registration (wywoływane podczas importu)
def register_builtin_languages():
    """Rejestruje wbudowane języki."""
    LanguageRegistry.register(Language.PYTHON, PythonLanguageStrategy())
    LanguageRegistry.register(Language.JAVASCRIPT, JavaScriptLanguageStrategy())
    LanguageRegistry.register(Language.TYPESCRIPT, TypeScriptLanguageStrategy())
    LanguageRegistry.register(Language.GO, GoLanguageStrategy())

register_builtin_languages()
```

**Przykład dodawania nowego języka (Rust)**:
```python
# ast/strategies/rust_strategy.py

class RustLanguageStrategy(LanguageStrategy):
    """Strategia dla Rust."""
    
    def get_function_query(self) -> str:
        return "(function_item) @function"
    
    def get_call_expression_query(self) -> str:
        return "(call_expression (identifier) @call)"
    
    def extract_function_name(self, node) -> str:
        for child in node.children:
            if child.type == "identifier":
                return child.text.decode("utf8")
        return "<anonymous>"
    
    def get_parser_name(self) -> str:
        return "rust"

# Dodaj enum value do Language
class Language(Enum):
    # ... existing ...
    RUST = "rust"

# Rejestracja
LanguageRegistry.register(Language.RUST, RustLanguageStrategy())

# That's it! TreeSitterParser automatycznie obsłuży Rust
```

**Korzyści Open/Closed**:
- ✅ Dodanie Rust = tylko nowy plik `rust_strategy.py`
- ✅ Brak modyfikacji `TreeSitterParser` (400+ linii kodu nie dotykane)
- ✅ Automatyczna rejestracja przez import
- ✅ Izolacja logic per-language (Single Responsibility)

### Adapter AST: TreeSitterParser

```python
class TreeSitterParser(ASTParser):
    """
    Parser AST z użyciem Tree-sitter.
    Ekstrakcja funkcji, call graph - do augmentacji kontekstu RAG.
    
    Używane w ReviewOrchestrator do:
    - Izolacji funkcji zmienionych w PR (context enhancement)
    - Budowy call graph (zależności między funkcjami)
    - Enrichment promptu o strukturę kodu
    
    Literatura: Meng2025RARe, Pornprasit2024FineTuningPromptingCR, Ren2025HydraReviewer
    """
    
    def __init__(self, language_registry: LanguageRegistry = None):
        """
        Inicjalizacja z użyciem LanguageRegistry (Open/Closed Principle).
        Parsery ładowane lazy per-language.
        """
        self.language_registry = language_registry or LanguageRegistry
        self.parsers: Dict[Language, Any] = {}  # Lazy loading
    
    def _get_or_load_parser(self, language: Language):
        """
        Lazy loading parsera dla języka (z LanguageRegistry).
        Open/Closed: nowe języki przez registry, nie hardcoded.
        """
        if language in self.parsers:
            return self.parsers[language]
        
        strategy = self.language_registry.get(language)
        if not strategy:
            raise UnsupportedLanguageException(
                f"Language {language.value} not supported. "
                f"Supported: {[l.value for l in self.language_registry.list_supported()]}"
            )
        
        import tree_sitter
        TSLanguage = tree_sitter.Language
        Parser = tree_sitter.Parser
        
        # Load compiled language library
        parser_name = strategy.get_parser_name()
        lang_lib = TSLanguage(f'build/languages.so', parser_name)
        parser = Parser()
        parser.set_language(lang_lib)
        
        self.parsers[language] = parser
        return parser
    
    def extract_functions(self, code: str, language: Language) -> List[FunctionNode]:
        """
        Ekstrakcja funkcji z kodu źródłowego.
        Zwraca listę węzłów funkcji z AST.
        Używa LanguageRegistry dla query patterns (Open/Closed).
        """
        parser = self._get_or_load_parser(language)
        strategy = self.language_registry.get(language)
        
        tree = parser.parse(bytes(code, "utf8"))
        root_node = tree.root_node
        
        # Query Tree-sitter - z strategy (Open/Closed)
        query_string = strategy.get_function_query()
        query = parser.language.query(query_string)
        captures = query.captures(root_node)
        
        return [
            FunctionNode(
                name=strategy.extract_function_name(capture[0]),
                start_line=capture[0].start_point[0],
                end_line=capture[0].end_point[0],
                body=code[capture[0].start_byte:capture[0].end_byte],
                language=language
            )
            for capture in captures
        ]
    
    def build_call_graph(self, functions: List[FunctionNode]) -> nx.DiGraph:
        """
        Budowa call graph z funkcji (dla augmentacji promptu).
        Wykrywanie wywołań funkcji wewnątrz ciała funkcji.
        """
        graph = nx.DiGraph()
        
        for func in functions:
            graph.add_node(func.name)
            
            # Parse body i wykryj call_expression nodes
            called_functions = self._extract_function_calls(func.body, func.language)
            for called in called_functions:
                if any(f.name == called for f in functions):
                    graph.add_edge(func.name, called)
        
        return graph
    
    def extract_changed_functions(self, diff: DiffHunk, code: str, language: Language) -> List[FunctionNode]:
        """
        Ekstrakcja tylko funkcji zmienionych w diff.
        Context enhancement - LLM widzi pełne funkcje, nie tylko fragmenty.
        """
        all_functions = self.extract_functions(code, language)
        changed_line_numbers = set(
            [line.new_line_number for line in diff.added_lines] +
            [line.old_line_number for line in diff.removed_lines]
        )
        
        # Filtruj funkcje które mają przecięcie ze zmienionymi liniami
        return [
            func for func in all_functions
            if any(line_num in changed_line_numbers 
                   for line_num in range(func.start_line, func.end_line + 1))
        ]
    
    # Removed: _get_function_query, _get_call_expression_query, _extract_function_name
    # Now handled by LanguageStrategy (Open/Closed Principle)
    
    def _extract_function_calls(self, code: str, language: Language) -> List[str]:
        """Wykrywa wywołania funkcji w kodzie (dla call graph). Używa strategy."""
        try:
            parser = self._get_or_load_parser(language)
            strategy = self.language_registry.get(language)
            if not strategy:
                return []
            
            tree = parser.parse(bytes(code, "utf8"))
            query_string = strategy.get_call_expression_query()
            query = parser.language.query(query_string)
            captures = query.captures(tree.root_node)
            
            return [capture[0].text.decode("utf8") for capture in captures]
        except UnsupportedLanguageException:
            return []
```

---

### Impact Analysis (Call Tree / Import Tree)

**Cel**: Wykrywanie potencjalnych skutków ubocznych zmian w kodzie poprzez analizę zależności.

#### Problem

Standardowy code review skupia się na zmienionych liniach (diff), ale nie bierze pod uwagę:
- Kto wywołuje zmienioną funkcję (callers)?
- Co może się zepsuć jeśli zmienimy sygnaturę metody?
- Czy usunięta metoda jest używana gdzie indziej?
- Czy zmiana semantyki funkcji wpływa na wywołujący kod?

**Przykład problemu**:
```python
# File: auth.py
def validate_token(token: str) -> bool:  # ← Zmieniono sygnaturę
-   return token.startswith("Bearer ")
+   return token.startswith("Bearer ") and len(token) > 20  # Nowy warunek
```

**Problem**: Kto wywołuje `validate_token()`? Czy nowy warunek może zepsuć istniejący kod?

#### Rozwiązanie: Dependency Analysis Port

Nowy port w domain layer dla analizy zależności:

```python
# domain/interfaces/dependency_analyzer.py

from abc import ABC, abstractmethod
from typing import List, Set
from dataclasses import dataclass

@dataclass
class CallSite:
    """Miejsce wywołania funkcji/metody."""
    file_path: FilePath
    line_number: int
    caller_name: str           # Nazwa funkcji/metody która wywołuje
    callee_name: str           # Nazwa funkcji/metody która jest wywoływana
    context: str               # Fragment kodu wokół wywołania (5 linii)

@dataclass
class ImportSite:
    """Miejsce importu modułu/funkcji."""
    file_path: FilePath
    line_number: int
    imported_module: str       # Nazwa importowanego modułu
    imported_names: List[str]  # Lista importowanych nazw (funkcje, klasy)
    context: str               # Fragment kodu importu

@dataclass
class ImpactAnalysisResult:
    """Wynik analizy wpływu zmiany."""
    changed_function: FunctionNode
    callers: List[CallSite]              # Kto wywołuje zmienioną funkcję (1 poziom)
    importers: List[ImportSite]          # Kto importuje moduł ze zmienioną funkcją
    potential_breaking_changes: List[str] # LLM analysis: co może się zepsuć
    severity: Severity                    # CRITICAL, HIGH, MEDIUM, LOW

class DependencyAnalyzer(ABC):
    """
    Port dla analizy zależności w kodzie (call tree, import tree).
    
    Używany w ReviewOrchestrator do:
    - Wykrywania potencjalnych breaking changes
    - Identyfikacji kodu dotkniętego zmianą (1 poziom głębi)
    - Analizy wpływu zmian w API
    
    Literatura: Ren2025HydraReviewer (call graph analysis)
    """
    
    @abstractmethod
    def find_callers(
        self, 
        function_name: str, 
        file_path: FilePath, 
        repository: str,
        language: Language
    ) -> List[CallSite]:
        """
        Znajduje wszystkie miejsca gdzie dana funkcja jest wywoływana (1 poziom głębi).
        
        Args:
            function_name: Nazwa funkcji do znalezienia
            file_path: Ścieżka do pliku gdzie funkcja jest zdefiniowana
            repository: Repozytorium (dla VCS context)
            language: Język programowania
        
        Returns:
            Lista miejsc wywołania funkcji
        """
        pass
    
    @abstractmethod
    def find_importers(
        self, 
        file_path: FilePath, 
        repository: str,
        language: Language
    ) -> List[ImportSite]:
        """
        Znajduje wszystkie pliki które importują dany moduł (1 poziom głębi).
        
        Args:
            file_path: Ścieżka do pliku/modułu
            repository: Repozytorium
            language: Język programowania
        
        Returns:
            Lista miejsc importu
        """
        pass
    
    @abstractmethod
    def analyze_impact(
        self,
        changed_function: FunctionNode,
        diff_hunk: DiffHunk,
        callers: List[CallSite],
        repository: str,
        llm: 'LLMProvider'
    ) -> ImpactAnalysisResult:
        """
        Analizuje wpływ zmiany funkcji na wywołujący kod (z pomocą LLM).
        
        Args:
            changed_function: Zmieniona funkcja (z AST)
            diff_hunk: Diff pokazujący co się zmieniło
            callers: Lista wywołań funkcji
            repository: Repozytorium
            llm: LLM provider do analizy semantycznej
        
        Returns:
            Wynik analizy wpływu z potencjalnymi problemami
        """
        pass
```

#### Adapter: TreeSitterDependencyAnalyzer

Implementacja using tree-sitter + grep search:

```python
# infrastructure/ast/tree_sitter_dependency_analyzer.py

class TreeSitterDependencyAnalyzer(DependencyAnalyzer):
    """
    Implementacja DependencyAnalyzer używając tree-sitter + grep.
    
    Strategia:
    1. Tree-sitter parsuje kod i buduje AST
    2. Query dla call_expression, import_statement
    3. Grep search dla szybkiego znalezienia candidates (optimization)
    4. Tree-sitter validacja candidates (false positive filter)
    """
    
    def __init__(
        self,
        vcs: VCSRepository,
        ast_parser: ASTParser,
        language_registry: LanguageRegistry
    ):
        self.vcs = vcs
        self.ast_parser = ast_parser
        self.language_registry = language_registry
    
    def find_callers(
        self, 
        function_name: str, 
        file_path: FilePath, 
        repository: str,
        language: Language
    ) -> List[CallSite]:
        """
        Znajduje wywołania funkcji w repozytorium.
        
        Algorytm:
        1. Grep search dla function_name w repo (szybkie znalezienie candidates)
        2. Dla każdego candidate: parse z tree-sitter
        3. Verify że to rzeczywiście call_expression (nie np. definicja)
        4. Extract context (5 linii wokół wywołania)
        """
        callers = []
        
        # Step 1: Grep search (fast)
        grep_results = self._grep_function_usage(repository, function_name, language)
        
        for file_path_candidate, line_num, line_content in grep_results:
            # Step 2: Parse file with tree-sitter (validate)
            try:
                file_content = self.vcs.fetch_file(repository, file_path_candidate, "HEAD")
                is_call = self._verify_is_call_site(
                    file_content, line_num, function_name, language
                )
                
                if is_call:
                    # Step 3: Extract context
                    context = self._extract_context(file_content, line_num, window=5)
                    caller_name = self._extract_caller_name(file_content, line_num, language)
                    
                    callers.append(CallSite(
                        file_path=file_path_candidate,
                        line_number=line_num,
                        caller_name=caller_name or "unknown",
                        callee_name=function_name,
                        context=context
                    ))
            except Exception as e:
                logger.warning(f"Could not analyze {file_path_candidate}: {e}")
                continue
        
        return callers
    
    def find_importers(
        self, 
        file_path: FilePath, 
        repository: str,
        language: Language
    ) -> List[ImportSite]:
        """
        Znajduje pliki które importują dany moduł.
        
        Algorytm:
        1. Determine module name from file_path (e.g., "auth.py" → "auth")
        2. Grep search dla "import auth" lub "from auth import"
        3. Parse z tree-sitter dla validation
        4. Extract imported names
        """
        importers = []
        module_name = self._file_path_to_module_name(file_path, language)
        
        # Grep patterns dla różnych języków
        import_patterns = self._get_import_patterns(module_name, language)
        
        for pattern in import_patterns:
            grep_results = self._grep_import_usage(repository, pattern, language)
            
            for file_path_candidate, line_num, line_content in grep_results:
                try:
                    file_content = self.vcs.fetch_file(repository, file_path_candidate, "HEAD")
                    imported_names = self._extract_imported_names(
                        file_content, line_num, module_name, language
                    )
                    
                    if imported_names:
                        context = self._extract_context(file_content, line_num, window=3)
                        
                        importers.append(ImportSite(
                            file_path=file_path_candidate,
                            line_number=line_num,
                            imported_module=module_name,
                            imported_names=imported_names,
                            context=context
                        ))
                except Exception as e:
                    logger.warning(f"Could not analyze imports in {file_path_candidate}: {e}")
                    continue
        
        return importers
    
    def analyze_impact(
        self,
        changed_function: FunctionNode,
        diff_hunk: DiffHunk,
        callers: List[CallSite],
        repository: str,
        llm: 'LLMProvider'
    ) -> ImpactAnalysisResult:
        """
        Używa LLM do analizy wpływu zmiany.
        
        LLM otrzymuje:
        - Changed function body (before/after)
        - Diff pokazujący co się zmieniło
        - Lista callers z kontekstem (gdzie funkcja jest używana)
        
        LLM analizuje:
        - Czy zmiana sygnатуry (parametry, return type)?
        - Czy zmiana semantyki (logika)?
        - Czy zmiana może zepsuć callers?
        - Sugeruje fixy dla callers jeśli potrzeba
        """
        prompt = self._build_impact_analysis_prompt(
            changed_function, diff_hunk, callers
        )
        
        llm_response = llm.generate_completion(prompt, temperature=0.2)
        
        # Parse LLM response (JSON)
        analysis = json.loads(llm_response)
        
        return ImpactAnalysisResult(
            changed_function=changed_function,
            callers=callers,
            importers=[],  # Filled later if needed
            potential_breaking_changes=analysis.get("breaking_changes", []),
            severity=self._parse_severity(analysis.get("severity", "medium"))
        )
    
    def _build_impact_analysis_prompt(
        self,
        changed_function: FunctionNode,
        diff_hunk: DiffHunk,
        callers: List[CallSite]
    ) -> str:
        """Buduje prompt dla LLM do analizy wpływu."""
        return f"""# Impact Analysis

## Changed Function: `{changed_function.name}`

### Diff (what changed):
```diff
{diff_hunk.content}
```

### Full Function Body (after change):
```{changed_function.language.value}
{changed_function.body}
```

## Callers (who uses this function):

{self._format_callers(callers)}

## Your Task:

Analyze whether this change can break the calling code. Consider:

1. **Signature changes**: parameters added/removed/renamed, return type changed
2. **Semantic changes**: logic changed, edge cases handled differently
3. **Contract changes**: preconditions, postconditions, invariants
4. **Side effects**: new exceptions thrown, new dependencies

For each caller, determine:
- Is it affected by the change? (yes/no)
- Why? (explanation)
- What can break? (specific scenario)
- How to fix? (suggestion for caller)

## Output Format (JSON):

{{
  "severity": "critical" | "high" | "medium" | "low",
  "breaking_changes": [
    {{
      "caller_file": "path/to/file.py",
      "caller_function": "function_name",
      "issue": "Description of what can break",
      "suggested_fix": "How to fix the caller code"
    }}
  ],
  "summary": "Overall assessment of impact"
}}

Output only valid JSON, no markdown.
"""
    
    def _format_callers(self, callers: List[CallSite]) -> str:
        """Formatuje callers do prompt."""
        if not callers:
            return "No callers found (unused function or private API)."
        
        formatted = []
        for i, caller in enumerate(callers, 1):
            formatted.append(f"""
### Caller {i}: `{caller.caller_name}` in {caller.file_path}

Line {caller.line_number}:
```
{caller.context}
```
""")
        return "\n".join(formatted)
    
    # Helper methods: _grep_function_usage, _verify_is_call_site, 
    # _extract_context, _extract_caller_name, etc.
    # (implementation omitted for brevity)
```

#### Integracja z ReviewOrchestrator

```python
class ReviewOrchestrator:
    """Rozszerzenie conduct_review() o impact analysis."""
    
    def __init__(
        self,
        vcs: VCSRepository,
        llm: LLMProvider,
        embedding_store: EmbeddingStore,
        config_loader: ConfigRepository,
        static_analyzer: Optional[StaticAnalyzer] = None,
        ast_parser: Optional[ASTParser] = None,
        dependency_analyzer: Optional[DependencyAnalyzer] = None  # ← Nowy
    ):
        # ... existing fields ...
        self.dependency_analyzer = dependency_analyzer
        self.enable_impact_analysis = dependency_analyzer is not None
    
    async def conduct_review(self, pr: PullRequest, config: ProjectConfig) -> ReviewResult:
        """
        Główny flow review z impact analysis.
        
        Nowe kroki:
        4a. Extract changed functions (AST) - już mamy
        4b. ← Nowy: Impact analysis dla każdej changed function
        4c. ← Nowy: LLM analizuje czy zmiana może zepsuć callers
        4d. ← Nowy: Dodaj komentarze ostrzeżenia jeśli wykryto problemy
        """
        # ... existing steps 1-4 ...
        
        # Step 4a: Extract changed functions (już mamy)
        changed_functions = []
        if self.ast_parser:
            for hunk in pr.diff_hunks:
                try:
                    code = self.vcs.fetch_file(pr.repository, hunk.file_path, pr.target_branch)
                    language = hunk.file_path.detect_language()
                    funcs = self.ast_parser.extract_changed_functions(hunk, code, language)
                    changed_functions.extend(funcs)
                except Exception as e:
                    logger.warning(f"Could not extract functions from {hunk.file_path}: {e}")
        
        # ========== NOWE: Step 4b-4d - Impact Analysis ==========
        impact_comments = []
        if self.enable_impact_analysis and changed_functions:
            logger.info(f"Running impact analysis for {len(changed_functions)} changed functions")
            
            for func in changed_functions:
                try:
                    # Step 4b: Find callers (1 level deep)
                    callers = self.dependency_analyzer.find_callers(
                        function_name=func.name,
                        file_path=func.file_path,
                        repository=pr.repository,
                        language=func.language
                    )
                    
                    if not callers:
                        logger.debug(f"No callers found for {func.name} (private or unused)")
                        continue
                    
                    logger.info(f"Found {len(callers)} callers for {func.name}")
                    
                    # Step 4c: LLM analyzes impact
                    diff_hunk = self._find_diff_for_function(pr.diff_hunks, func)
                    impact_result = self.dependency_analyzer.analyze_impact(
                        changed_function=func,
                        diff_hunk=diff_hunk,
                        callers=callers,
                        repository=pr.repository,
                        llm=self.llm
                    )
                    
                    # Step 4d: Create warning comments if breaking changes detected
                    if impact_result.potential_breaking_changes:
                        for breaking_change in impact_result.potential_breaking_changes:
                            impact_comments.append(ReviewComment(
                                file_path=func.file_path,
                                line_number=func.start_line,
                                body=self._format_impact_warning(
                                    func.name, breaking_change, impact_result.severity
                                ),
                                severity=impact_result.severity,
                                source=CommentSource.IMPACT_ANALYSIS
                            ))
                
                except Exception as e:
                    logger.error(f"Impact analysis failed for {func.name}: {e}")
                    continue
        
        # Merge impact comments z existing comments
        all_comments = comments + impact_comments
        
        # ... rest of existing flow ...
        
        return ReviewResult(
            pull_request=pr,
            comments=all_comments,
            requires_human_review=any(c.severity == Severity.CRITICAL for c in all_comments),
            metrics={
                "total_comments": len(all_comments),
                "impact_warnings": len(impact_comments),
                "changed_functions_analyzed": len(changed_functions)
            }
        )
    
    def _format_impact_warning(
        self, 
        function_name: str, 
        breaking_change: dict,
        severity: Severity
    ) -> str:
        """Formatuje komentarz ostrzeżenia o impact."""
        emoji = "🔴" if severity == Severity.CRITICAL else "⚠️"
        
        return f"""{emoji} **IMPACT WARNING** - Breaking Change Detected

Function `{function_name}` is called in other places. This change may break:

**Affected:** `{breaking_change['caller_function']}` in [{breaking_change['caller_file']}]

**Issue:** {breaking_change['issue']}

**Suggested fix for caller:**
```python
{breaking_change['suggested_fix']}
```

**Severity:** {severity.value.upper()}

Please verify that all calling code is updated accordingly, or add tests to catch potential breakage.
"""
    
    def _find_diff_for_function(self, hunks: List[DiffHunk], func: FunctionNode) -> DiffHunk:
        """Znajduje diff hunk zawierający daną funkcję."""
        for hunk in hunks:
            if hunk.file_path == func.file_path:
                # Check if func lines overlap with hunk lines
                hunk_lines = set(range(hunk.new_start_line, hunk.new_start_line + hunk.new_line_count))
                func_lines = set(range(func.start_line, func.end_line + 1))
                if hunk_lines & func_lines:
                    return hunk
        return None
```

#### Przykład: End-to-End Flow z Impact Analysis

```
1. Developer zmienia funkcję validate_token() w auth.py:
   - Remove parameter `user_id`
   - Change return type str → bool
   
2. GitHub webhook → ACR system
   
3. ReviewOrchestrator.conduct_review():
   
   a. AST Parser: extract_changed_functions()
      → [FunctionNode(name="validate_token", file="auth.py", lines=42-50)]
   
   b. DependencyAnalyzer.find_callers("validate_token", "auth.py")
      - Grep search: "validate_token" in repository
      - Found 3 callers:
        * handlers/login.py:156 (in `handle_login()`)
        * middleware/auth_middleware.py:78 (in `authenticate()`)
        * tests/test_auth.py:234 (in `test_invalid_token()`)
   
   c. DependencyAnalyzer.analyze_impact():
      LLM receives:
      ```
      ## Changed Function: validate_token
      
      ### Diff:
      - def validate_token(token: str, user_id: int) -> str:
      + def validate_token(token: str) -> bool:
            ...
      
      ### Callers:
      1. handle_login() in handlers/login.py:156
         result = validate_token(request.token, request.user_id)
         
      2. authenticate() in middleware/auth_middleware.py:78
         token_valid = validate_token(token, current_user.id)
      ```
      
      LLM analyzes:
      {
        "severity": "critical",
        "breaking_changes": [
          {
            "caller_file": "handlers/login.py",
            "caller_function": "handle_login",
            "issue": "Function signature changed - removed user_id parameter. Caller still passes user_id.",
            "suggested_fix": "result = validate_token(request.token)  # Remove user_id argument"
          },
          {
            "caller_file": "middleware/auth_middleware.py",
            "caller_function": "authenticate",
            "issue": "Return type changed from str to bool. Caller may expect string.",
            "suggested_fix": "Check usage of token_valid - if expecting string, update logic"
          }
        ]
      }
   
   d. Create impact warning comments:
      🔴 Comment on auth.py:42 (function definition):
      """
      IMPACT WARNING - Breaking Change Detected
      
      Function `validate_token` is called in other places. This change may break:
      
      **Affected:** `handle_login` in handlers/login.py
      
      **Issue:** Function signature changed - removed user_id parameter. 
      Caller still passes user_id.
      
      **Suggested fix for caller:**
      ```
      result = validate_token(request.token)  # Remove user_id argument
      ```
      
      **Severity:** CRITICAL
      """
   
4. Developer vidzi komentarz i naprawia callers przed merge
```

#### Konfiguracja w `.acr-config.yml`

```yaml
impact_analysis:
  enabled: true
  max_callers_per_function: 10      # Limit analizy (performance)
  depth: 1                           # Tylko 1 poziom głębi (direct callers)
  analyze_imports: true              # Czy analizować import tree
  severity_threshold: medium         # Publikuj tylko >= medium
  exclude_patterns:                  # Exclude z analizy
    - "tests/**"                     # Nie analizuj test files
    - "**/*_test.py"
    - "migrations/**"
```

#### Literatura i motywacja

**Papers:**
- **Ren2025HydraReviewer**: Call graph analysis dla wykrywania cross-file dependencies
- **Meng2025RARe**: Context expansion przez dependency tracking
- **Pornprasit2024FineTuningPromptingCR**: Function isolation dla context enhancement

**Korzyści:**
1. **Wykrycie breaking changes** - automatyczne wykrywanie zmian API
2. **Reduced regression** - mniej bugów po merge (broken callers)
3. **Better context** - LLM widzi nie tylko diff, ale też usage context
4. **Proactive review** - ostrzeżenia PRZED merge, nie po deploy
5. **Cross-file awareness** - review nie ograniczony do zmienionych plików

**Trade-offs:**
- ⚠️ **Performance**: Grep + tree-sitter parsowanie może być wolne dla dużych repo
- ⚠️ **Accuracy**: Może być false positives (np. funkcje o tej samej nazwie)
- ⚠️ **Cost**: Dodatkowe wywołania LLM dla impact analysis (można limitować)

**Mitigation strategies:**
- Limit do top-5 most changed functions (sorted by diff size)
- Cache callers per function (TTL 1h)
- Run impact analysis tylko jeśli `impact_analysis.enabled: true` w config
- Depth=1 tylko (nie recursive call graph)

---

### Adapter Config: YAMLConfigLoader

```python
class YAMLConfigLoader(ConfigRepository):
    """
    Implementacja portu ConfigRepository - wczytywanie konfiguracji z .acr-config.yml.
    Wszystkie standardy kodowania, konwencje nazewnictwa i reguły biznesowe 
    są ładowane z repozytorium (nie hardcodowane).
    """
    
    def __init__(self, vcs_adapter: VCSRepository, cache_ttl: int = 3600):
        self.vcs = vcs_adapter
        self.cache: Dict[str, ProjectConfig] = {}
        self.cache_ttl = cache_ttl
        self.cache_timestamps: Dict[str, datetime] = {}
    
    def get_config(self, repository: str) -> ProjectConfig:
        """
        Pobiera konfigurację projektu z .acr-config.yml w repozytorium.
        Cachuje wynik (domyślnie 1h TTL).
        """
        # Check cache
        if repository in self.cache:
            cached_at = self.cache_timestamps[repository]
            if (datetime.now() - cached_at).total_seconds() < self.cache_ttl:
                logger.debug(f"Config cache HIT for {repository}")
                return self.cache[repository]
        
        # Fetch from VCS
        logger.info(f"Fetching .acr-config.yml from {repository}")
        try:
            config_content = self.vcs.fetch_file(repository, ".acr-config.yml", branch="main")
        except FileNotFoundError:
            logger.warning(f"No .acr-config.yml found in {repository}, using defaults")
            return self._default_config()
        
        # Parse YAML
        config_dict = yaml.safe_load(config_content)
        
        # Parse general rule sets (text-based, LLM-friendly)
        general_rule_sets = [
            RuleSet(
                name=rs["name"],
                enabled=rs.get("enabled", True),
                rules_text=rs["rules"]
            )
            for rs in config_dict["review"].get("rule_sets", [])
        ]
        
        # Parse file pattern rules (glob matching)
        file_pattern_rules = []
        for fpr in config_dict["review"].get("file_patterns", []):
            # Parse optional LLM override
            llm_override = None
            if "llm" in fpr:
                llm_override = LLMConfig(
                    provider=fpr["llm"].get("provider", config_dict["llm"]["provider"]),
                    model=fpr["llm"].get("model", config_dict["llm"]["model"]),
                    temperature=fpr["llm"].get("temperature", config_dict["llm"]["temperature"]),
                    max_tokens=fpr["llm"].get("max_tokens", config_dict["llm"]["max_tokens"])
                )
            
            # Parse optional RAG override
            rag_override = None
            if "rag" in fpr:
                rag_override = RAGConfig(
                    enabled=fpr["rag"].get("enabled", config_dict["rag"]["enabled"]),
                    top_k=fpr["rag"].get("top_k", config_dict["rag"]["top_k"]),
                    documentation_paths=fpr["rag"].get("documentation_paths", []),
                    architectural_docs=fpr["rag"].get("architectural_docs", [])
                )
            
            file_pattern_rules.append(
                FilePatternRule(
                    pattern=fpr["pattern"],
                    rules_text=fpr["rules"],
                    priority=fpr.get("priority", 0),
                    llm_config=llm_override,
                    rag_config=rag_override
                )
            )
        
        # Build ProjectConfig with text-based rules
        project_config = ProjectConfig(
            name=config_dict["project"]["name"],
            languages=config_dict["project"]["languages"],
            severity_threshold=Severity[config_dict["review"]["severity_threshold"]],
            human_threshold=config_dict["review"]["human_threshold"],
            max_chunk_size=config_dict["review"].get("max_chunk_size", 500),
            
            # LLM config (global, mo\u017ce by\u0107 nadpisany przez file_patterns.llm)
            llm_provider=config_dict["llm"]["provider"],
            llm_model=config_dict["llm"]["model"],
            llm_temperature=config_dict["llm"].get("temperature", 0.3),
            llm_max_tokens=config_dict["llm"].get("max_tokens", 2000),
            language_models=config_dict["llm"].get("language_models", {}),
            
            # RAG config (global, mo\u017ce by\u0107 nadpisany przez file_patterns.rag)
            rag_enabled=config_dict["rag"]["enabled"],
            rag_top_k=config_dict["rag"]["top_k"],
            documentation_paths=config_dict["rag"].get("documentation_paths", []),
            architectural_doc_paths=config_dict["rag"].get("architectural_docs", []),
            
            # Rule sets (text-based, flexible)
            general_rule_sets=general_rule_sets,
            file_pattern_rules=file_pattern_rules,
            
            # Static analysis
            static_analysis_enabled=config_dict["static_analysis"]["enabled"],
            static_analysis_tools=config_dict["static_analysis"]["tools"]
        )
        
        # Cache
        self.cache[repository] = project_config
        self.cache_timestamps[repository] = datetime.now()
        
        logger.info(
            f"Loaded config for {repository}: "
            f"{len(project_config.general_rule_sets)} general rule sets, "
            f"{len(project_config.file_pattern_rules)} file pattern rules, "
            f"{len(project_config.architectural_doc_paths)} architectural docs"
        )
        
        return project_config
    
    def _default_config(self) -> ProjectConfig:
        """Domyślna konfiguracja gdy brak .acr-config.yml."""
        return ProjectConfig(
            name="default",
            languages=["python"],
            severity_threshold=Severity.WARNING,
            human_threshold=1,
            max_chunk_size=500,
            llm_provider="openai",
            llm_model="gpt-4o",
            llm_temperature=0.3,
            llm_max_tokens=2000,
            language_models={},
            rag_enabled=True,
            rag_top_k=5,
            documentation_paths=["README.md"],
            architectural_doc_paths=[],
            general_rule_sets=[],  # Brak własnych zasad
            file_pattern_rules=[],
            static_analysis_enabled=False,
            static_analysis_tools={}
        )
    
    def invalidate_cache(self, repository: str) -> None:
        """Invalidacja cache dla repozytorium (np. po zmianie .acr-config.yml)."""
        if repository in self.cache:
            del self.cache[repository]
            del self.cache_timestamps[repository]
            logger.info(f"Invalidated config cache for {repository}")
```

---

## Warstwa Presentation (API + CLI)

### API: WebhookHandlers (FastAPI)

```python
from fastapi import FastAPI, Request, BackgroundTasks

app = FastAPI(title="ACR System API")

@app.post("/webhooks/github")
async def handle_github_webhook(
    request: Request, 
    background_tasks: BackgroundTasks,
    use_case: ProcessPullRequestUseCase = Depends(get_process_pr_use_case)
):
    """
    Webhook endpoint dla GitHub.
    Odbiera zdarzenia: pull_request.opened, pull_request.synchronize
    """
    payload = await request.json()
    event_type = request.headers.get("X-GitHub-Event")
    
    if event_type == "pull_request" and payload["action"] in ["opened", "synchronize"]:
        pr_id = f"{payload['repository']['full_name']}/pull/{payload['pull_request']['number']}"
        
        # Asynchroniczne przetwarzanie w tle (CI/CD)
        background_tasks.add_task(
            execute_review_async,
            use_case=use_case,
            pr_id=pr_id
        )
        
        return {"status": "accepted", "pr_id": pr_id}
    
    return {"status": "ignored"}

async def execute_review_async(use_case: ProcessPullRequestUseCase, pr_id: str):
    """Wykonanie review w tle (nie blokuje webhooka)."""
    try:
        request = PRReviewRequest(pr_id=pr_id)
        result = use_case.execute(request)
        logger.info(f"Review completed for {pr_id}: {len(result.comments)} comments")
    except Exception as e:
        logger.error(f"Review failed for {pr_id}: {e}")
```

### CLI: ReviewCommand (Click)

```python
import click

@click.group()
def cli():
    """ACR System CLI."""
    pass

@cli.command()
@click.argument("pr_id")
@click.option("--config", default=".acr-config.yml", help="Path to config file")
def review(pr_id: str, config: str):
    """
    Ręczne uruchomienie review dla PR.
    
    Example:
        acr review octocat/Hello-World/pull/42
    """
    # Bootstrap dependencies
    container = bootstrap_container(config)
    use_case = container.resolve(ProcessPullRequestUseCase)
    
    # Execute
    request = PRReviewRequest(pr_id=pr_id)
    result = use_case.execute(request)
    
    # Display results
    click.echo(f"Review completed: {len(result.comments)} comments")
    for comment in result.comments:
        click.echo(f"  [{comment.severity.name}] {comment.file_path}:{comment.line_number}")
        click.echo(f"    {comment.message}")

@cli.command()
@click.argument("repo")
def index(repo: str):
    """
    Indeksowanie repozytorium do RAG.
    
    Example:
        acr index octocat/Hello-World
    """
    # Bootstrap
    container = bootstrap_container()
    context_builder = container.resolve(ContextBuilder)
    
    # Index
    context_builder.build_from_repository(repo)
    click.echo(f"Repository {repo} indexed successfully")
```

---

## Konfiguracja per-projekt: `.acr-config.yml`

```yaml
# .acr-config.yml - Plik w głównym katalogu repozytorium

project:
  name: "my-awesome-app"
  languages:
    - python
    - javascript

review:
  severity_threshold: WARNING  # Minimalna severity dla publikacji
  human_threshold: 1           # Liczba CRITICAL issues wymagająca HITL
  max_chunk_size: 500          # Max linii kodu na chunk (dla dużych PR)
  
  # Ogólne zestawy zasad (text-based, LLM-friendly)
  rule_sets:
    - name: "Code Quality"
      enabled: true
      rules: |
        - Follow SOLID principles: Single Responsibility, Open/Closed, Liskov Substitution, Interface Segregation, Dependency Inversion
        - Keep functions small and focused (max 50 lines)
        - Use meaningful variable and function names
        - Avoid deep nesting (max 3 levels)
        - Prefer composition over inheritance
        - Write self-documenting code
    
    - name: "Security"
      enabled: true
      rules: |
        - Never commit secrets, API keys, passwords, or tokens
        - Always validate and sanitize user inputs
        - Use parameterized queries for SQL (prevent SQL injection)
        - Implement proper authentication and authorization
        - Use HTTPS for all external communications
        - Follow OWASP Top 10 guidelines
    
    - name: "Performance"
      enabled: true
      rules: |
        - Avoid N+1 query problems
        - Use database indexes for frequently queried columns
        - Cache expensive computations
        - Use async/await for I/O operations
        - Avoid blocking the main thread
    
    - name: "Testing"
      enabled: false  # Opcjonalnie wyłączone
      rules: |
        - All public APIs must have unit tests
        - Aim for 80%+ code coverage
        - Use AAA pattern (Arrange-Act-Assert)
        - Mock external dependencies in tests
  
  # Zasady per file pattern (glob matching)
  file_patterns:
    - pattern: "*.ts"
      rules: |
        - Follow Airbnub TypeScript Style Guide
        - Use strict TypeScript compiler options
        - Prefer interfaces over type aliases for object shapes
        - Avoid using 'any' type
        - Use const assertions where appropriate
    
    - pattern: "*/Domain/*.ts"
      priority: 10  # Wyższy priorytet (domain layer jest krytyczny)
      rules: |
        - Domain entities must be immutable
        - No dependencies on Infrastructure or Presentation layers
        - Use value objects for typed primitives (Email, PhoneNumber, Money)
        - Domain logic must be testable without external dependencies
        - Follow DDD tactical patterns (Aggregates, Repositories, Domain Events)
      
      # LLM override - domenowa logika wymaga Claude (lepsze architektoniczne reasoning)
      llm:
        provider: anthropic
        model: claude-3-5-sonnet
        temperature: 0.2  # Niższa temperatura dla krytycznego domain layera
        max_tokens: 3000
      
      # RAG override - dołączaj dokumentację DDD
      rag:
        top_k: 10  # Więcej kontekstu dla domain layer
        architectural_docs:
          - docs/ARCHITECTURE.md
          - docs/DDD_GUIDELINES.md
          - docs/ADR/*.md
    
    - pattern: "*/Infrastructure/*.ts"
      rules: |
        - All external I/O must go through adapters
        - Implement retry logic with exponential backoff
        - Use circuit breakers for external services
        - Log all external API calls with context
      
      # RAG override - dołączaj dokumentację zewnętrznych API
      rag:
        architectural_docs:
          - docs/EXTERNAL_APIs.md
          - docs/INTEGRATION_PATTERNS.md
    
    - pattern: "**/*.test.ts"
      rules: |
        - Tests must use AAA pattern (Arrange-Act-Assert)
        - Test names should describe behavior, not implementation
        - Use descriptive test data (avoid magic values)
        - Mock external dependencies
        - One assertion per test (or logical group)
      
      # LLM override - testy nie wymagają najlepszego modelu (oszczędność kosztów)
      llm:
        model: gpt-4o-mini
        temperature: 0.4
      
      # RAG override - brak historical reviews dla testów
      rag:
        enabled: false
    
    - pattern: "*.py"
      rules: |
        - Follow PEP 8 style guide
        - Use type hints for all function signatures
        - Max line length: 88 characters (Black formatter)
        - Use dataclasses for simple data containers
        - Prefer f-strings over .format() or %
    
    - pattern: "*/api/*.py"
      rules: |
        - All API endpoints must have input validation (Pydantic)
        - Return proper HTTP status codes
        - Use async/await for all I/O operations
        - Include OpenAPI documentation (docstrings)
        - Implement proper error handling with meaningful messages
      
      # LLM override - API wymaga modelu z dobrym rozumieniem async/await
      llm:
        model: gpt-4o
        temperature: 0.2  # Niższa temperatura dla bezpieczeństwa API
      
      # RAG override - dołączaj dokumentację API
      rag:
        top_k: 8
        architectural_docs:
          - docs/API_DESIGN.md
          - docs/SECURITY_GUIDELINES.md
          - .github/API_STANDARDS.md

# Globalna konfiguracja LLM (domyślna, nadpisywana przez file_patterns.llm)
llm:
  provider: openai              # openai | anthropic | custom
  model: gpt-4o                 # Domyślny model
  temperature: 0.3
  max_tokens: 2000
  
  # Model selection per language (opcjonalne, nadpisywane przez file_patterns.llm)
  language_models:
    python: gpt-4o
    javascript: claude-3-5-sonnet
    go: gpt-4-turbo

# Globalna konfiguracja RAG (domyślna, nadpisywana przez file_patterns.rag)
rag:
  enabled: true
  top_k: 5                      # Top-k retrieval dla similarity search
  include_historical_reviews: true
  
  # Dokumentacja do indeksowania (RAG similarity search)
  documentation_paths:
    - docs/
    - README.md
    - CONTRIBUTING.md
  
  # Dokumenty architektoniczne dołączane zawsze (full content, nie retrieval)
  # Obsługuje glob patterns (docs/ADR/*.md)
  architectural_docs:
    - docs/ARCHITECTURE.md
    - docs/CODING_STANDARDS.md
    - docs/ADR/*.md              # Architecture Decision Records
    - CONTRIBUTING.md
    - .github/PULL_REQUEST_TEMPLATE.md

static_analysis:
  enabled: true
  
  # Nazwy GitHub Checks / GitLab CI jobs do monitorowania
  # System pobiera wyniki z tych checks zamiast uruchamiać narzędzia samodzielnie
  github_check_names:
    - "Ruff"              # GitHub Action: ruff check
    - "mypy"              # GitHub Action: mypy
    - "ESLint"            # GitHub Action: eslint
    - "Pylint"            # Opcjonalnie
    - "pytest"            # Opcjonalnie - test failures
  
  gitlab_job_names:
    - "lint:python"       # GitLab CI job dla Ruff
    - "lint:typescript"   # GitLab CI job dla ESLint
    - "test:static"       # GitLab CI job dla mypy
  
  # Timeout - maksymalny czas oczekiwania na zakończenie CI (sekundy)
  ci_timeout: 300  # 5 minut

integration:
  platform: github              # github | gitlab
  webhook_secret: ${WEBHOOK_SECRET}
  auto_publish: true            # Czy publikować komentarze automatycznie
```

---

## Dependency Injection (Bootstrapping)

```python
# dependency_injection.py

from typing import Protocol
import os

class Container:
    """Prosty DI container dla systemu."""
    
    def __init__(self, config_path: str = ".acr-config.yml"):
        self.config = self._load_config(config_path)
        self._instances = {}
    
    def resolve(self, interface_type: type):
        """Rozwiązanie zależności dla danego typu."""
        if interface_type in self._instances:
            return self._instances[interface_type]
        
        # Rejestracja adapterów na podstawie konfiguracji
        if interface_type == VCSRepository:
            if self.config["integration"]["platform"] == "github":
                instance = GitHubAdapter(
                    token=os.getenv("GITHUB_TOKEN"),
                    base_url="https://api.github.com"
                )
            elif self.config["integration"]["platform"] == "gitlab":
                instance = GitLabAdapter(
                    token=os.getenv("GITLAB_TOKEN"),
                    base_url="https://gitlab.com/api/v4"
                )
            else:
                raise ValueError(f"Unknown platform: {self.config['integration']['platform']}")
        
        elif interface_type == LLMProvider:
            # Open/Closed Principle: używamy factory zamiast if/elif
            provider_name = self.config["llm"]["provider"]
            instance = LLMProviderFactory.create(
                provider_name,
                api_key=os.getenv(f"{provider_name.upper()}_API_KEY"),
                model=self.config["llm"].get("model")
            )
        
        elif interface_type == EmbeddingStore:
            instance = FAISSStore(
                embedding_service=EmbeddingService(model="text-embedding-3-small"),
                index_path=".acr_index/"
            )
        
        elif interface_type == StaticAnalyzer:
            # Adapter pobierający wyniki z CI/CD zamiast uruchamiać narzędzia
            if self.config["integration"]["platform"] == "github":
                instance = GitHubChecksAdapter(
                    token=os.getenv("GITHUB_TOKEN"),
                    base_url="https://api.github.com"
                )
            elif self.config["integration"]["platform"] == "gitlab":
                instance = GitLabCIAdapter(
                    token=os.getenv("GITLAB_TOKEN"),
                    base_url="https://gitlab.com/api/v4"
                )
            else:
                raise ValueError(f"No StaticAnalyzer for platform: {self.config['integration']['platform']}")
        
        elif interface_type == ASTParser:
            # Tree-sitter parser dla ekstrakcji funkcji i call graph
            instance = TreeSitterParser()
        
        elif interface_type == ReviewOrchestrator:
            instance = ReviewOrchestrator(
                vcs_repo=self.resolve(VCSRepository),
                llm_provider=self.resolve(LLMProvider),
                embedding_store=self.resolve(EmbeddingStore),
                static_analyzer=self.resolve(StaticAnalyzer),
                ast_parser=self.resolve(ASTParser),
                config_repo=YAMLConfigLoader(self.config)
            )
        
        elif interface_type == ProcessPullRequestUseCase:
            instance = ProcessPullRequestUseCase(
                review_orchestrator=self.resolve(ReviewOrchestrator)
            )
        
        else:
            raise ValueError(f"Cannot resolve: {interface_type}")
        
        self._instances[interface_type] = instance
        return instance

def bootstrap_container(config_path: str = ".acr-config.yml") -> Container:
    """Factory function dla DI container."""
    return Container(config_path)
```

---

## Flow wykonania (End-to-End)

### Scenariusz 1: Webhook GitHub → Automatyczny Review (mały PR)

```
1. Developer tworzy PR na GitHubie (120 linii zmian)
   ↓
2. GitHub wysyła webhook POST /webhooks/github
   ↓
3. WebhookHandler parsuje payload i tworzy PRReviewRequest
   ↓
4. ProcessPullRequestUseCase.execute() uruchamia review w tle (BackgroundTask)
   ↓
5. ReviewOrchestrator.conduct_review():
   a. GitHubAdapter.fetch_pull_request() → pobiera PR i diff
   b. Sprawdzenie: pr.should_chunk() → FALSE (120 < 500 linii)
   c. YAMLConfigLoader.get_config() → wczytuje .acr-config.yml z repo
   d. ContextBuilder.build_context() → RAG retrieval (FAISS top-5)
      + extract_rules_from_config() → general_rules, file_pattern_rules
      + **TreeSitterParser.extract_changed_functions()** → ekstrakcja funkcji z diff (AST)
        * Przykład: `def calculate_discount(price, rate)` (linie 42-58) z payment.py
        * Context enhancement: LLM widzi pełne funkcje, nie tylko diff fragments
        * Literatura: Meng2025RARe (RAG top-5), Pornprasit2024 (Tree-sitter)
   e. GitHubChecksAdapter.fetch_ci_results() → pobiera luźno zebrane wyniki z CI (różne formaty)
   f. **LLM Parsing CI Results** (pomocniczy LLM - tańszy model):
      + _parse_ci_results_with_llm(raw_results, diff, changed_files)
      + Prompt: "Parse these CI outputs, extract issues for changed files"
      + LLM zwraca structured JSON: [{file, line, severity, message, is_in_diff}]
      + Filtrowanie: tylko issues w changed files/lines
      + Output: List[ParsedCIIssue] - sparsowane, przefiltrowane
   g. Dodanie parsed issues do context.parsed_ci_issues
   h. OpenAIAdapter.generate_review() → GPT-4o z pełnym kontekstem:
      + RAG (dokumentacja, historical reviews)
      + Standardy z konfigu (general rules, file patterns)
      + **Extracted functions (Tree-sitter AST)** - pełny kontekst funkcji
      + Parsed CI issues (już przefiltrowane, tylko relevantne)
   i. Merge + rank comments
   j. Sprawdzenie human-in-the-loop threshold
   ↓
6. GitHubAdapter.publish_comments() → POST inline comments do PR
   ↓
7. MetricsLogger.log() → zapis metryk (BLEU, cost, latency)
   ↓
8. Developer widzi komentarze w PR na GitHubie
```

### Scenariusz 2: Duży PR z chunkowaniem (1500 linii)

```
1. Developer tworzy duży PR na GitHubie (1500 linii zmian, 50 plików)
   ↓
2. GitHub wysyła webhook POST /webhooks/github
   ↓
3. WebhookHandler parsuje payload → PRReviewRequest
   ↓
4. ProcessPullRequestUseCase.execute() → uruchomienie w tle
   ↓
5. ReviewOrchestrator.conduct_review():
   a. GitHubAdapter.fetch_pull_request() → pobiera PR
   b. Sprawdzenie: pr.should_chunk(max_lines=500) → TRUE (1500 > 500)
   c. redirect → _conduct_chunked_review()
   ↓
6. ReviewOrchestrator._conduct_chunked_review():
   a. pr.create_chunks(chunk_size=500) → 3 chunki:
      - Chunk 0: files 1-18 (490 linii)
      - Chunk 1: files 19-35 (505 linii)
      - Chunk 2: files 36-50 (505 linii)
   b. YAMLConfigLoader.get_config() → wczytuje .acr-config.yml
   c. ContextBuilder.build_context() → RAG + standardy
      + **TreeSitterParser.extract_changed_functions()** → ekstrakcja top-5 funkcji (AST)
   d. GitHubChecksAdapter.fetch_ci_results() → raw CI outputs (raz dla całego PR)
   e. **LLM Parsing CI Results** (raz dla całego PR):
      + _parse_ci_results_with_llm(raw_results, diff, changed_files)
      + Parsuje wszystkie raw CI outputs → List[ParsedCIIssue]
   f. Loop przez chunki:
      • Chunk 0:
        - Filtruj parsed_ci_issues do files 1-18 (dla relevance)
        - Twórz chunk_context (base_context + filtered parsed_ci_issues)
        - OpenAIAdapter.generate_review(chunk_0_diff, chunk_context) → GPT-4o
          * LLM widzi w kontekście: "[ERROR] Ruff (F401): Unused import in file_5.py:42"
          * Issues już sparsowane i przefiltrowane przez pomocniczy LLM
        - Akumulacja komentarzy
      • Chunk 1:
        - Filtruj parsed_ci_issues do files 19-35
        - chunk_context z filtered issues
        - OpenAIAdapter.generate_review(chunk_1_diff, chunk_context) → GPT-4o
        - Akumulacja komentarzy
      • Chunk 2:
        - Filtruj parsed_ci_issues do files 36-50
        - chunk_context z filtered issues
        - OpenAIAdapter.generate_review(chunk_2_diff, chunk_context) → GPT-4o
        - Akumulacja komentarzy
   g. _deduplicate_comments() → usunięcie duplikatów (ten sam plik/linia)
   h. _rank_by_severity() → ranking komentarzy
   g. Sprawdzenie human-in-the-loop threshold
   ↓
7. GitHubAdapter.publish_comments() → POST wszystkich komentarzy (z 3 chunków)
   ↓
8. MetricsLogger.log() → zapis metryk:
   - chunked: true
   - chunk_count: 3
   - total_cost: sum(chunk_costs)
   ↓
9. Developer widzi skonsolidowane komentarze w PR
```

### Scenariusz 3: PR z per-file LLM/RAG overrides (Domain + Tests)

```
1. Developer tworzy PR (250 linii zmian):
   - src/Domain/User.ts (150 linii) - domena użytkowników  
   - tests/Domain/User.test.ts (100 linii) - testy
   ↓
2. GitHub wysyła webhook POST /webhooks/github
   ↓
3. WebhookHandler parsuje payload → PRReviewRequest
   ↓
4. ProcessPullRequestUseCase.execute() → uruchomienie w tle
   ↓
5. ReviewOrchestrator.conduct_review():
   a. GitHubAdapter.fetch_pull_request() → pobiera PR
   b. Sprawdzenie: pr.should_chunk() → FALSE (250 < 500 linii)
   c. YAMLConfigLoader.get_config() → wczytuje .acr-config.yml
   d. _select_llm_config(changed_files=[src/Domain/User.ts, tests/Domain/User.test.ts]):
      • Sprawdza file_patterns dla każdego pliku
      • src/Domain/User.ts matches "*/Domain/*.ts" (priority=10) 
        → llm_config: Claude-3.5-Sonnet, temp=0.2, max_tokens=3000
      • tests/Domain/User.test.ts matches "**/*.test.ts" (priority=0)
        → llm_config: GPT-4o-mini, temp=0.4
      • Wybiera najwyższy priorytet → Claude-3.5-Sonnet (priority=10)
      • Logger: "Using LLM override: claude-3-5-sonnet (priority 10)"
   e. _select_rag_config(changed_files=[src/Domain/User.ts, tests/Domain/User.test.ts]):
      • src/Domain/User.ts matches "*/Domain/*.ts"
        → rag_config: top_k=10, architectural_docs=[docs/ARCHITECTURE.md, docs/DDD_GUIDELINES.md, docs/ADR/*.md]
      • tests/Domain/User.test.ts matches "**/*.test.ts"
        → rag_config: enabled=false
      • Wybiera najwyższy priorytet → top_k=10 + DDD docs (priority=10)
      • Logger: "Using RAG override: top_k=10, docs=3 (priority 10)"
   f. _build_context(pr, config, rag_config_override):
      • RAG retrieval: top_k=10 (zamiast default 5)
      • Fetch architectural_docs:
        - docs/ARCHITECTURE.md
        - docs/DDD_GUIDELINES.md
        - docs/ADR/001-domain-model.md
        - docs/ADR/002-value-objects.md
      • General rules: Security, Performance, Code Quality
      • File-specific rules: DDD tactical patterns dla */Domain/*.ts
   g. GitHubChecksAdapter.fetch_ci_results() → raw CI outputs (różne formaty)
   h. **LLM Parsing CI Results** (pomocniczy LLM):
      • Parsuje raw outputs z ESLint, TypeScript Compiler
      • Wyodrębnia issues tylko dla changed files
      • Output: [ParsedCIIssue(file="src/Domain/User.ts", line=42, code="explicit-function-return-type", ...)]
   i. Dodaje parsed_ci_issues do context
   j. AnthropicAdapter.generate_review() z pełnym kontekstem:
      • Fetch luźno zebrane wyniki z GitHub Checks API (różne formaty)
      • exemple: CIToolResult(tool_name="Ruff", raw_output="src/file.py:42: F401 unused import...")
   h. AnthropicAdapter.generate_review() z pełnym kontekstem:
      • Model: claude-3-5-sonnet (zamiast default gpt-4o)
      • Temperature: 0.2 (zamiast default 0.3)
      • Max tokens: 3000 (zamiast default 2000)
      • Context: RAG top-10 + DDD guidelines + domain-specific rules + CI results
      • Prompt sekcje:
        - General Rules (Security, Performance, Quality)
        - File-Specific Rules (DDD patterns)
        - Static Analysis Results: "mypy found: Missing return type at line 42"
        - Instructions: "Consider CI findings, suggest fixes, identify other issues"
      • LLM generuje komentarze uwzględniając CI (bez osobnego merge)
   i. Rank comments (LLM już zinterpretował CI issues)
   j. Metadata zapisuje: llm_model="claude-3-5-sonnet", rag_top_k=10
   ↓
6. GitHubAdapter.publish_comments() → POST komentarzy z domain expertise
   ↓
7. MetricsLogger.log() → zapis metryk:
   - llm_model: "claude-3-5-sonnet"
   - rag_override: true
   - rag_top_k: 10
   - architectural_docs_count: 4
   - cost: $0.045 (Claude drozszy niż GPT-4o)
   ↓
8. Developer widzi komentarze z głęboką wiedzą DDD (dzięki Claude + DDD docs)
```

### Scenariusz 4: PR z Impact Analysis - Wykrycie Breaking Change

```
1. Developer zmienia funkcję validate_token() w auth.py:
   - Usuwa parametr user_id
   - Zmienia return type: str → bool
   - PR: 80 linii zmian (1 plik)
   ↓
2. GitHub wysyła webhook POST /webhooks/github
   ↓
3. WebhookHandler parsuje payload → PRReviewRequest
   ↓
4. ProcessPullRequestUseCase.execute() → uruchomienie w tle
   ↓
5. ReviewOrchestrator.conduct_review() (z Impact Analysis):
   a. GitHubAdapter.fetch_pull_request() → pobiera PR
   b. Diff parsing: DiffHunk(file="auth.py", lines=42-50, changes=8)
   c. ProjectConfig loading: impact_analysis.enabled=true
   d. RAG retrieval: top-3 docs (AUTH.md, SECURITY_BEST_PRACTICES.md)
   ↓
   e. **AST Parsing** (TreeSitterAdapter):
      - extract_changed_functions(diff, full_code, Language.PYTHON)
      - Result: [FunctionNode(name="validate_token", file="auth.py", lines=42-50)]
   ↓
   f. **Impact Analysis** (TreeSitterDependencyAnalyzer):
      1. find_callers("validate_token", "auth.py")
         - Grep search: "validate_token" across repository
         - Found candidates:
           * handlers/login.py:156
           * middleware/auth_middleware.py:78
           * tests/test_auth.py:234
         - Tree-sitter validation (filter string occurrences, comments)
         - Confirmed callers (3):
           * CallSite(file="handlers/login.py", line=156, 
                      caller="handle_login", 
                      context="result = validate_token(request.token, request.user_id)")
           * CallSite(file="middleware/auth_middleware.py", line=78,
                      caller="authenticate",
                      context="token_valid = validate_token(token, current_user.id)")
           * CallSite(file="tests/test_auth.py", line=234,
                      caller="test_invalid_token",
                      context="assert not validate_token(bad_token, user.id)")
      ↓
      2. analyze_impact(changed_function, diff, callers, llm)
         - LLM prompt:
           ```
           ## Changed Function: validate_token
           
           ### Diff:
           - def validate_token(token: str, user_id: int) -> str:
           + def validate_token(token: str) -> bool:
                   ...
           
           ### Callers:
           1. handle_login() in handlers/login.py:156
              result = validate_token(request.token, request.user_id)
           
           2. authenticate() in middleware/auth_middleware.py:78
              token_valid = validate_token(token, current_user.id)
           
           Analyze breaking changes...
           ```
         - LLM analysis (GPT-4o):
           ```json
           {
             "severity": "critical",
             "breaking_changes": [
               {
                 "caller_file": "handlers/login.py",
                 "caller_function": "handle_login",
                 "issue": "Signature changed - removed user_id parameter. Caller passes 2 args, function expects 1.",
                 "suggested_fix": "result = validate_token(request.token)  # Remove user_id"
               },
               {
                 "caller_file": "middleware/auth_middleware.py",
                 "caller_function": "authenticate",
                 "issue": "Return type changed str → bool. Variable token_valid may expect string.",
                 "suggested_fix": "Verify usage of token_valid - update if expecting string"
               }
             ],
             "summary": "Critical breaking changes detected. 2 callers affected by signature and return type changes."
           }
           ```
      ↓
      3. Create Impact Warning Comments:
         - Comment 1 (auth.py:42):
           🔴 **IMPACT WARNING** - Breaking Change Detected
           
           Function `validate_token` is called in other places. This change may break:
           
           **Affected:** `handle_login` in [handlers/login.py](handlers/login.py:156)
           
           **Issue:** Signature changed - removed user_id parameter. 
           Caller passes 2 args, function expects 1.
           
           **Suggested fix for caller:**
           ```python
           result = validate_token(request.token)  # Remove user_id
           ```
           
           **Severity:** CRITICAL
           
           Please update all calling code or add migration layer.
         
         - Comment 2 (auth.py:42):
           (similar for middleware/auth_middleware.py)
   ↓
   g. Standard LLM Review (OpenAIAdapter):
      - Prompt includes: diff + RAG context + rules + impact_warnings
      - LLM generates additional comments:
        * Line 44: "Consider adding type hint for return value"
        * Line 47: "Token validation should include expiry check"
   ↓
   h. Merge comments:
      - Impact warnings (2) + standard review (2) = 4 total comments
      - Deduplicate if overlap
   ↓
6. GitHubAdapter.publish_comments():
   - POST /repos/.../pulls/.../comments
   - 2 impact warnings (CRITICAL severity)
   - 2 standard review comments (MEDIUM severity)
   ↓
7. MetricsLogger.log():
   - impact_analysis_enabled: true
   - changed_functions_analyzed: 1
   - callers_found: 3
   - breaking_changes_detected: 2
   - impact_analysis_duration: 4.2s
   - llm_calls: 2 (1 for impact, 1 for standard review)
   - total_cost: $0.008
   ↓
8. Developer widzi komentarze:
   - ⚠️ Impact warnings wskazują dokładnie gdzie kod się zepsuje
   - 💡 Konkretne suggested fixes dla każdego caller
   - ✅ Standard review comments jako bonus
   ↓
9. Developer fixuje callers przed merge:
   - Update handlers/login.py (remove user_id arg)
   - Update middleware/auth_middleware.py (update return handling)
   - Update tests/test_auth.py (fix assertion)
   ↓
10. Push kolejny commit → nowy webhook → re-review:
    - Impact analysis: no breaking changes detected (callers fixed)
    - ✅ Review approved
```

**Korzyści tego scenariusza:**
- 🎯 **Proactive detection**: Breaking changes wykryte PRZED merge (nie po deploy)
- 🎯 **Actionable feedback**: Konkretne file:line do fix + suggested code
- 🎯 **Time saving**: Developer nie musi ręcznie szukać wszystkich callers
- 🎯 **Reduced regression**: 0 broken code po merge (wszystkie callers fixed)
- 🎯 **Cross-file awareness**: Review nie ograniczony do auth.py (widzi całe repo)

**Metryki z tego scenariusza:**
- Callers found: 3 (2 production, 1 test)
- Breaking changes detected: 2 (signature + return type)
- False positives: 0 (tree-sitter validation works)
- Time to analyze: 4.2s (grep 0.8s + AST parsing 2.1s + LLM 1.3s)
- Cost: $0.008 ($0.003 impact analysis + $0.005 standard review)
- Developer time saved: ~15 minutes (no manual caller search)

---

## Testowanie architektury

### Testy jednostkowe (Domain Layer)

```python
# tests/domain/test_review_orchestrator.py

class MockVCSRepository(VCSRepository):
    """Mock adapter VCS dla testów."""
    
    def fetch_pull_request(self, pr_id: str) -> PullRequest:
        return PullRequest(
            id=pr_id,
            repository="test/repo",
            source_branch="feature",
            target_branch="main",
            author="testuser",
            diff_hunks=[],
            metadata={}
        )
    
    # ... inne metody

def test_review_orchestrator_conducts_full_review():
    """Test: ReviewOrchestrator wykonuje pełny cykl review."""
    
    # Arrange
    mock_vcs = MockVCSRepository()
    mock_llm = MockLLMProvider()
    mock_rag = MockEmbeddingStore()
    mock_analyzer = MockStaticAnalyzer()
    mock_config = MockConfigRepository()
    
    orchestrator = ReviewOrchestrator(
        vcs_repo=mock_vcs,
        llm_provider=mock_llm,
        embedding_store=mock_rag,
        static_analyzer=mock_analyzer,
        config_repo=mock_config
    )
    
    # Act
    result = orchestrator.conduct_review("test/repo/pull/1")
    
    # Assert
    assert len(result.comments) > 0
    assert result.requires_human_review is False
```

### Testy integracyjne (Infrastructure Layer)

```python
# tests/infrastructure/test_github_adapter.py

@pytest.mark.integration
def test_github_adapter_fetches_real_pr():
    """Test integracyjny: GitHubAdapter pobiera prawdziwy PR z API."""
    
    adapter = GitHubAdapter(
        token=os.getenv("GITHUB_TEST_TOKEN"),
        base_url="https://api.github.com"
    )
    
    pr = adapter.fetch_pull_request("octocat/Hello-World/pull/1")
    
    assert pr.id == "octocat/Hello-World/pull/1"
    assert pr.repository == "octocat/Hello-World"
    assert len(pr.diff_hunks) > 0

@pytest.mark.integration
def test_github_adapter_handles_pagination_for_large_pr():
    """Test integracyjny: GitHubAdapter poprawnie paginuje duże PR (100+ plików)."""
    
    adapter = GitHubAdapter(
        token=os.getenv("GITHUB_TEST_TOKEN"),
        base_url="https://api.github.com"
    )
    
    # PR z >100 plikami (wymaga paginacji)
    pr = adapter.fetch_pull_request("large-repo/massive-refactor/pull/42")
    
    assert len(pr.diff_hunks) > 100
    # Weryfikacja że wszystkie pliki zostały pobrane
```

### Testy jednostkowe (chunkowanie)

```python
# tests/domain/test_pull_request_chunking.py

def test_pull_request_should_chunk_for_large_changes():
    """Test: PullRequest poprawnie wykrywa konieczność chunkowania."""
    
    # Arrange
    large_pr = PullRequest(
        id="test/repo/pull/1",
        repository="test/repo",
        source_branch="feature",
        target_branch="main",
        author="testuser",
        diff_hunks=[
            DiffHunk(
                file_path=FilePath(f"file_{i}.py"),
                added_lines=["line"] * 50,  # 50 linii added
                removed_lines=["line"] * 30  # 30 linii removed
            )
            for i in range(10)  # 10 plików × 80 linii = 800 linii total
        ],
        total_changes=800,
        metadata={}
    )
    
    # Act & Assert
    assert large_pr.should_chunk(max_lines_per_chunk=500) is True
    assert large_pr.should_chunk(max_lines_per_chunk=1000) is False

def test_pull_request_creates_correct_chunks():
    """Test: PullRequest dzieli się na poprawne chunki."""
    
    # Arrange
    pr = PullRequest(
        id="test/repo/pull/1",
        repository="test/repo",
        source_branch="feature",
        target_branch="main",
        author="testuser",
        diff_hunks=[
            DiffHunk(file_path=FilePath(f"file_{i}.py"), added_lines=["x"] * 100, removed_lines=[])
            for i in range(8)  # 8 plików × 100 linii = 800 linii
        ],
        total_changes=800,
        metadata={}
    )
    
    # Act
    chunks = pr.create_chunks(chunk_size=300)
    
    # Assert
    assert len(chunks) == 3  # 800 / 300 = ~3 chunki
    assert chunks[0].chunk_index == 0
    assert chunks[1].chunk_index == 1
    assert chunks[2].chunk_index == 2
    
    # Każdy chunk ≤ 300 linii (z wyjątkiem ostatniego, który może być mniejszy)
    assert chunks[0].total_changes() <= 300
    assert chunks[1].total_changes() <= 300
    assert chunks[2].total_changes() <= 300
    
    # Suma linii w chunkach = total PR
    total_chunked = sum(chunk.total_changes() for chunk in chunks)
    assert total_chunked == pr.total_changes

def test_review_orchestrator_conducts_chunked_review():
    """Test: ReviewOrchestrator poprawnie wykonuje review z chunkowaniem."""
    
    # Arrange
    mock_vcs = MockVCSRepository()
    mock_vcs.set_large_pr(pr_id="test/repo/pull/1", total_changes=1500)
    
    mock_config = MockConfigRepository()
    mock_config.set_max_chunk_size(500)
    
    mock_llm = MockLLMProvider()
    
    orchestrator = ReviewOrchestrator(
        vcs_repo=mock_vcs,
        llm_provider=mock_llm,
        embedding_store=MockEmbeddingStore(),
        static_analyzer=MockStaticAnalyzer(),
        config_repo=mock_config
    )
    
    # Act
    result = orchestrator.conduct_review("test/repo/pull/1")
    
    # Assert
    assert result.metadata["chunked"] is True
    assert result.metadata["chunk_count"] == 3  # 1500 / 500 = 3
    assert len(result.comments) > 0
    
    # Weryfikacja że LLM został wywołany 3 razy (raz na chunk)
    assert mock_llm.call_count == 3
```

### Testy integracyjne (GitHub Checks API)

```python
# tests/infrastructure/test_github_checks_adapter.py

@pytest.mark.integration
def test_github_checks_adapter_fetches_ci_results():
    """Test integracyjny: GitHubChecksAdapter pobiera wyniki CI z GitHub Checks API."""
    
    adapter = GitHubChecksAdapter(
        token=os.getenv("GITHUB_TEST_TOKEN"),
        base_url="https://api.github.com"
    )
    
    # PR z uruchomionym CI (Ruff, mypy)
    pr = PullRequest(
        id="octocat/Hello-World/pull/42",
        repository="octocat/Hello-World",
        head_sha="abc123def456",
        source_branch="feature",
        target_branch="main",
        author="testuser",
        diff_hunks=[],
        metadata={}
    )
    
    # Fetch CI results
    results = adapter.fetch_ci_results(pr)
    
    # Assertions
    assert len(results) > 0
    assert all(isinstance(result, CIToolResult) for result in results)
    assert all(result.tool_name in ["Ruff", "mypy", "ESLint"] for result in results)
    
    # Verify result structure (luźno zebrane wyniki)
    first_result = results[0]
    assert first_result.tool_name is not None
    assert first_result.status in ["success", "failure", "cancelled"]
    assert len(first_result.raw_output) > 0
    assert isinstance(first_result.files_mentioned, set)

@pytest.mark.integration
def test_github_checks_adapter_waits_for_ci_completion():
    """Test integracyjny: GitHubChecksAdapter czeka na zakończenie CI."""
    
    adapter = GitHubChecksAdapter(
        token=os.getenv("GITHUB_TEST_TOKEN"),
        base_url="https://api.github.com"
    )
    
    # PR z CI w trakcie wykonywania
    pr = PullRequest(
        id="octocat/Hello-World/pull/43",
        repository="octocat/Hello-World",
        head_sha="running_ci_sha",
        source_branch="feature",
        target_branch="main",
        author="testuser",
        diff_hunks=[],
        metadata={}
    )
    
    # Check CI status
    is_completed = adapter.is_ci_completed(pr)
    
    # Jeśli CI się wykonuje, powinno wrócić False
    if not is_completed:
        assert is_completed is False
        # Wait and check again
        time.sleep(30)
        is_completed_after_wait = adapter.is_ci_completed(pr)
        # Po czasie powinno się zakończyć (albo timeout)

@pytest.mark.unit
def test_github_checks_adapter_maps_severity_correctly():
    """Test jednostkowy: GitHubChecksAdapter poprawnie mapuje severity."""
    
    adapter = GitHubChecksAdapter(
        token="test_token",
        base_url="https://api.github.com"
    )
    
    # Test mapping
    assert adapter._map_severity("notice") == Severity.INFO
    assert adapter._map_severity("warning") == Severity.WARNING
    assert adapter._map_severity("failure") == Severity.ERROR
    assert adapter._map_severity("unknown") == Severity.WARNING  # default

@pytest.mark.unit
def test_review_orchestrator_parses_ci_results():
    """Test jednostkowy: ReviewOrchestrator parsuje CI results przez pomocniczy LLM."""
    
    # Arrange
    mock_vcs = MockVCSRepository()
    mock_llm = MockLLMProvider()
    mock_rag = MockEmbeddingStore()
    
    # Mock StaticAnalyzer (GitHubChecksAdapter)
    mock_analyzer = Mock(spec=StaticAnalyzer)
    mock_analyzer.is_ci_completed.return_value = True
    mock_analyzer.fetch_ci_results.return_value = [
        CIToolResult(
            tool_name="Ruff",
            status="failure",
            raw_output="main.py:42: F401: Unused import: typing.Optional\n",
            files_mentioned={"main.py"},
            conclusion="failed"
        )
    ]
    
    # Mock LLM parsing response
    mock_llm.parse_ci_output.return_value = json.dumps({
        "issues": [
            {
                "tool_name": "Ruff",
                "file_path": "main.py",
                "line_number": 42,
                "severity": "error",
                "issue_code": "F401",
                "message": "Unused import: typing.Optional",
                "suggestion": "Remove the unused import",
                "is_in_diff": True
            }
        ]
    })
    
    mock_config = MockConfigRepository()
    
    orchestrator = ReviewOrchestrator(
        vcs_repo=mock_vcs,
        llm_provider=mock_llm,
        embedding_store=mock_rag,
        static_analyzer=mock_analyzer,
        config_repo=mock_config
    )
    
    # Act
    result = orchestrator.conduct_review("test/repo/pull/1")
    
    # Assert
    mock_analyzer.is_ci_completed.assert_called_once()
    mock_analyzer.fetch_ci_results.assert_called_once()
    
    # Verify LLM parsing was called
    assert mock_llm.parse_ci_output.called
    
    # Verify parsed CI issues were provided to main LLM as context
    assert mock_llm.generate_review.called
    call_args = mock_llm.generate_review.call_args
    context = call_args[1]["context"]  # keyword argument
    assert len(context.parsed_ci_issues) >= 1
    assert context.parsed_ci_issues[0].file_path == "main.py"
    assert context.parsed_ci_issues[0].line_number == 42
    assert context.parsed_ci_issues[0].message == "Unused import: typing.Optional"
    
    # LLM generates comments considering parsed CI issues
    # We don't expect separate STATIC_ANALYSIS source comments
    assert all(c.source != CommentSource.STATIC_ANALYSIS for c in result.comments)
```

### Testy jednostkowe (Tree-sitter AST extraction)

```python
# tests/ast/test_tree_sitter_parser.py

def test_tree_sitter_extracts_functions_from_python():
    """Test: TreeSitterParser ekstrakcja funkcji z kodu Python."""
    
    # Arrange
    parser = TreeSitterParser()
    code = """
def calculate_discount(price, rate):
    if rate < 0 or rate > 1:
        raise ValueError("Rate must be between 0 and 1")
    return price * (1 - rate)

def apply_coupon(order, coupon_code):
    discount_rate = get_discount_rate(coupon_code)
    order.total = calculate_discount(order.total, discount_rate)
    return order
"""
    
    # Act
    functions = parser.extract_functions(code, Language.PYTHON)
    
    # Assert
    assert len(functions) == 2
    assert functions[0].name == "calculate_discount"
    assert functions[0].start_line == 1
    assert functions[1].name == "apply_coupon"
    assert "discount_rate = get_discount_rate" in functions[1].body

def test_tree_sitter_extracts_only_changed_functions():
    """Test: extract_changed_functions zwraca tylko funkcje z changami w diff."""
    
    # Arrange
    parser = TreeSitterParser()
    
    # Pełny plik z 3 funkcjami
    full_code = """
def func_a():  # lines 1-2
    return "a"

def func_b():  # lines 4-6 (CHANGED)
    return "b_modified"

def func_c():  # lines 8-9
    return "c"
"""
    
    # Diff hunk - tylko func_b zmieniona (linia 5)
    diff = DiffHunk(
        file_path=FilePath("test.py"),
        added_lines=[DiffLine(new_line_number=5, content='    return "b_modified"')],
        removed_lines=[DiffLine(old_line_number=5, content='    return "b"')],
        start_line=4,
        end_line=6
    )
    
    # Act
    changed_functions = parser.extract_changed_functions(diff, full_code, Language.PYTHON)
    
    # Assert
    assert len(changed_functions) == 1
    assert changed_functions[0].name == "func_b"
    assert 'return "b_modified"' in changed_functions[0].body

def test_review_orchestrator_extracts_functions_to_context():
    """Test: ReviewOrchestrator dodaje extracted functions do CodeContext."""
    
    # Arrange
    mock_vcs = MockVCSRepository()
    mock_vcs.set_file_content("test/repo", "main.py", "def foo(): pass\ndef bar(): pass")
    
    mock_ast = Mock(spec=ASTParser)
    mock_ast.extract_changed_functions.return_value = [
        FunctionNode(name="foo", start_line=1, end_line=1, body="def foo(): pass", language=Language.PYTHON)
    ]
    
    orchestrator = ReviewOrchestrator(
        vcs_repo=mock_vcs,
        llm_provider=MockLLMProvider(),
        embedding_store=MockEmbeddingStore(),
        static_analyzer=MockStaticAnalyzer(),
        ast_parser=mock_ast,
        config_repo=MockConfigRepository()
    )
    
    # Act
    result = orchestrator.conduct_review("test/repo/pull/1")
    
    # Assert
    assert mock_ast.extract_changed_functions.called
    
    # Verify context passed to LLM contains extracted functions
    call_args = orchestrator.llm.generate_review.call_args
    context = call_args[1]["context"]
    assert len(context.extracted_functions) == 1
    assert context.extracted_functions[0].name == "foo"
```

### Testy Open/Closed Principle (Factory + Registry)

```python
# tests/patterns/test_llm_provider_factory.py

def test_llm_provider_factory_creates_openai():
    """Test: LLMProviderFactory tworzy OpenAIAdapter."""
    
    # Act
    provider = LLMProviderFactory.create(
        "openai",
        api_key="test-key",
        model="gpt-4o"
    )
    
    # Assert
    assert isinstance(provider, OpenAIAdapter)
    assert provider.model == "gpt-4o"

def test_llm_provider_factory_creates_anthropic():
    """Test: LLMProviderFactory tworzy AnthropicAdapter."""
    
    # Act
    provider = LLMProviderFactory.create(
        "anthropic",
        api_key="test-key",
        model="claude-3.5-sonnet"
    )
    
    # Assert
    assert isinstance(provider, AnthropicAdapter)
    assert provider.model == "claude-3.5-sonnet"

def test_llm_provider_factory_raises_for_unknown():
    """Test: LLMProviderFactory rzuca ValueError dla nieznanego providera."""
    
    # Act & Assert
    with pytest.raises(ValueError, match="Unknown LLM provider: unknown_provider"):
        LLMProviderFactory.create("unknown_provider", api_key="test")

def test_llm_provider_factory_allows_custom_registration():
    """Test: Można zarejestrować custom providera (Open/Closed)."""
    
    # Arrange
    class CustomLLMProvider(LLMProvider):
        def __init__(self, api_key: str, model: str = "custom-model"):
            self.api_key = api_key
            self.model = model
        
        def generate_review(self, diff, context, config):
            return []
        
        def parse_ci_output(self, prompt, response_format="json"):
            return "{}"
        
        def estimate_cost(self, input_tokens, output_tokens, model=None):
            return 0.0
    
    # Act
    LLMProviderFactory.register("custom", CustomLLMProvider)
    provider = LLMProviderFactory.create("custom", api_key="test-key")
    
    # Assert
    assert isinstance(provider, CustomLLMProvider)
    assert provider.model == "custom-model"
    assert "custom" in LLMProviderFactory.list_providers()

def test_container_uses_factory_for_llm_provider():
    """Test: Container używa LLMProviderFactory (nie if/elif)."""
    
    # Arrange
    config = {
        "llm": {"provider": "openai", "model": "gpt-4o"},
        "integration": {"platform": "github"}
    }
    container = Container(config)
    
    # Act
    provider = container.resolve(LLMProvider)
    
    # Assert
    assert isinstance(provider, OpenAIAdapter)
    # Brak if/elif w Container - używa factory

# tests/patterns/test_language_registry.py

def test_language_registry_returns_python_strategy():
    """Test: LanguageRegistry zwraca PythonLanguageStrategy."""
    
    # Act
    strategy = LanguageRegistry.get(Language.PYTHON)
    
    # Assert
    assert isinstance(strategy, PythonLanguageStrategy)
    assert strategy.get_function_query() == "(function_definition) @function"
    assert strategy.get_parser_name() == "python"

def test_language_registry_supports_javascript():
    """Test: LanguageRegistry wspiera JavaScript."""
    
    # Act
    strategy = LanguageRegistry.get(Language.JAVASCRIPT)
    
    # Assert
    assert isinstance(strategy, JavaScriptLanguageStrategy)
    assert strategy.get_function_query() == "(function_declaration) @function"

def test_language_registry_allows_custom_language():
    """Test: Można zarejestrować custom język (Open/Closed)."""
    
    # Arrange
    class RustLanguageStrategy(LanguageStrategy):
        def get_function_query(self) -> str:
            return "(function_item) @function"
        
        def get_call_expression_query(self) -> str:
            return "(call_expression (identifier) @call)"
        
        def extract_function_name(self, node) -> str:
            return "rust_func"
        
        def get_parser_name(self) -> str:
            return "rust"
    
    # Act
    LanguageRegistry.register(Language.RUST, RustLanguageStrategy())
    strategy = LanguageRegistry.get(Language.RUST)
    
    # Assert
    assert isinstance(strategy, RustLanguageStrategy)
    assert strategy.get_function_query() == "(function_item) @function"
    assert Language.RUST in LanguageRegistry.list_supported()

def test_tree_sitter_parser_uses_registry():
    """Test: TreeSitterParser używa LanguageRegistry (nie hardcoded dict)."""
    
    # Arrange
    parser = TreeSitterParser()
    code = "def test(): pass"
    
    # Mock LanguageRegistry to verify it's used
    with patch.object(LanguageRegistry, 'get') as mock_get:
        mock_strategy = Mock(spec=LanguageStrategy)
        mock_strategy.get_function_query.return_value = "(function_definition) @function"
        mock_strategy.extract_function_name.return_value = "test"
        mock_get.return_value = mock_strategy
        
        # Act
        try:
            functions = parser.extract_functions(code, Language.PYTHON)
        except:
            pass  # May fail due to mock, but we verify registry call
        
        # Assert
        mock_get.assert_called_with(Language.PYTHON)
        # TreeSitterParser deleguje do registry, nie używa if/elif

def test_adding_new_language_doesnt_modify_tree_sitter_parser():
    """Test: Dodanie nowego języka nie wymaga modyfikacji TreeSitterParser."""
    
    # Arrange - symulacja dodania Kotlin
    class KotlinLanguageStrategy(LanguageStrategy):
        def get_function_query(self) -> str:
            return "(function_declaration) @function"
        
        def get_call_expression_query(self) -> str:
            return "(call_expression) @call"
        
        def extract_function_name(self, node) -> str:
            return "kotlin_func"
        
        def get_parser_name(self) -> str:
            return "kotlin"
    
    # Act - rejestracja (bez modyfikacji TreeSitterParser!)
    Language.KOTLIN = "kotlin"  # Dodaj enum value
    LanguageRegistry.register(Language.KOTLIN, KotlinLanguageStrategy())
    
    # Assert - TreeSitterParser automatycznie obsługuje Kotlin
    parser = TreeSitterParser()
    assert LanguageRegistry.is_supported(Language.KOTLIN)
    strategy = LanguageRegistry.get(Language.KOTLIN)
    assert strategy.get_parser_name() == "kotlin"
    
    # Weryfikacja: TreeSitterParser kod niezmieniony
    # (brak konieczności modyfikacji 150+ linii kodu)
```

**Korzyści testowania z OCP**:
- ✅ **Izolacja testów**: Test tylko nowego providera/języka, nie całego systemu
- ✅ **Szybkie testy**: Mock factory/registry, nie integracyjne
- ✅ **Zero regresji**: Dodanie Gemini/Rust nie wymaga re-testu OpenAI/Python
- ✅ **Clear failures**: Test `test_gemini_adapter` fails → problem w Gemini, nie w core

---

## Metryki i monitoring

System loguje następujące metryki zgodnie z literaturą:

1. **BLEU-4**: porównanie komentarzy LLM z historycznymi (ground truth)
2. **BERTScore**: semantyczna similarity komentarzy
3. **Human evaluation**: ocena praktyków (relevance, information, clarity) w skali 1-5
4. **Cost tracking**: koszt wywołań API (tokeny × cena)
5. **Latency**: czas wykonania review (end-to-end)
6. **Regression ratio**: % przypadków gdzie LLM pogorszył kod (testy jednostkowe)

```python
# infrastructure/metrics_logger.py

class MetricsLogger:
    """Logowanie metryk zgodnie z metodyką z literatury."""
    
    def log_review_metrics(self, result: ReviewResult, ground_truth: List[ReviewComment] = None):
        """
        Loguje metryki do Prometheus/CloudWatch/CSV.
        """
        metrics = {
            "timestamp": datetime.now().isoformat(),
            "pr_id": result.pr_id,
            "comment_count": len(result.comments),
            "cost_usd": result.metadata["cost"],
            "latency_seconds": result.metadata["latency"],
            "requires_human": result.requires_human_review
        }
        
        if ground_truth:
            metrics["bleu_4"] = self._calculate_bleu(result.comments, ground_truth)
            metrics["bert_score"] = self._calculate_bert_score(result.comments, ground_truth)
        
        self._write_metrics(metrics)
```

---

## Wnioski architektoniczne

### Zalety architektury heksagonalnej dla ACR

1. **Wymienność dostawców**: łatwa zmiana GitHub → GitLab, GPT-4 → Claude bez zmian w logice domenowej
2. **Testowalność**: domain logic testowalna bez zewnętrznych zależności (mocks)
3. **Separacja concerns**: logika review odizolowana od szczegółów HTTP, JSON, API
4. **Konfigurowalność**: `.acr-config.yml` jako single source of truth
5. **Rozszerzalność**: nowe adaptery (BitBucket, Copilot) bez wpływu na core
6. **Skalowalność**: chunkowanie dużych PR umożliwia przetwarzanie nawet bardzo dużych zmian (1000+ plików)

### Obsługa dużych Pull Requestów

**Problem**: PR z 1500+ liniami zmian przekracza context window LLM i generuje wysokie koszty API.

**Rozwiązanie - chunkowanie**:
- Automatyczne wykrycie dużych PR (`pr.should_chunk(max_lines=500)`)
- Podział na chunki o rozmiarze konfigurownym (domyślnie 500 linii)
- Sekwencyjne przetwarzanie chunków z tym samym kontekstem bazowym
- Deduplikacja komentarzy dla plików występujących w wielu chunkach
- Agregacja kosztów i metadanych

**Korzyści**:
- Możliwość review PR o dowolnym rozmiarze
- Kontrola kosztów API (każdy chunk ≤ max tokens)
- Równoległa możliwość przetwarzania chunków (opcjonalna optymalizacja)
- Lepsza jakość review (mniejszy kontekst = bardziej fokusowane komentarze)

### Integracja z CI/CD dla statycznej analizy

**Problem**: Uruchamianie narzędzi statycznej analizy (Ruff, mypy, ESLint) bezpośrednio w systemie ACR prowadzi do:
- Duplikacji pracy (narzędzia już działają w CI/CD)
- Opóźnień (czekanie na wykonanie analizy)
- Złożoności instalacji i konfiguracji
- Niezgodności środowisk (ACR vs projektowe CI)

**Rozwiązanie - dwustopniowy proces z LLM parsing**:
1. **Fetch raw CI results** z GitHub Checks API / GitLab CI artifacts
2. **LLM Parsing** (pomocniczy model - GPT-4o-mini): parsuje różne formaty, filtruje do changed files
3. **Główny LLM review**: dostaje sparsowane, przefiltrowane issues w structured format

- Reużywa istniejących pipeline'ów CI/CD (GitHub Actions, GitLab CI)
- Wait for CI completion z konfiguowalnym timeout (domyślnie 300s)
- **Krok pośredni LLM**: elastyczne parsowanie różnych formatów (JSON, text, logs)
- **Automatyczne filtrowanie**: tylko issues w changed files/lines
- **Główny LLM**: dostaje clean, structured input zamiast raw outputs
- **LLM interpretuje CI results**: potwierdza, wyjaśnia, sugeruje fixy, wykrywa false positives

**Kroki techniczne**:
1. **GitHub**: `GET /repos/{owner}/{repo}/commits/{sha}/check-runs`
   - Pobiera check-runs (Ruff, mypy, ESLint)
   - `GET /repos/{owner}/{repo}/check-runs/{id}/annotations`
   - Format: `{file, line, severity, message}`
   
2. **GitLab**: `GET /projects/{id}/pipelines/{pipeline_id}/jobs`
   - Pobiera joby z pipeline (lint:python, test:static)
   - `GET /projects/{id}/jobs/{job_id}/artifacts` (JSON format)
   - LUB `GET /projects/{id}/jobs/{job_id}/trace` (log parsing)

**Korzyści nowego podejścia**:
- ✅ **Zero duplikacji** - narzędzia uruchamiane raz (w CI)
- ✅ **Szybkość** - ACR nie czeka na wykonanie analizy, tylko na zakończenie CI
- ✅ **Prostota** - brak instalacji Ruff/mypy/ESLint w ACR
- ✅ **Spójność** - te same wyniki co widzą developerzy w CI
- ✅ **Rozszerzalność** - łatwo dodać nowe narzędzia (wystarczy dodać nazwę check/job)
- ✅ **Cache'owanie** - GitHub/GitLab cache'ują wyniki CI
- ✅ **Elastyczność formatów** - system przyjmuje **różne formaty wyników** (JSON, text, logs):
  * Niektóre narzędzia dostarczają structured annotations z line numbers
  * Inne tylko tekstowy output per plik
  * Jeszcze inne tylko ogólne logi bez szczegółów
  * **Pomocniczy LLM parsuje wszystkie** - elastyczne, bez sztywnego parsingu per tool
  * Brak wymuszonej struktury = łatwiejsza integracja z dowolnym narzędziem
- ✅ **Automatyczne filtrowanie** (przez pomocniczy LLM):
  * Tylko issues w changed files
  * Oznaczanie is_in_diff (czy issue w zmienionych liniach)
  * Mniejszy prompt dla głównego LLM = niższe koszty
  * Lepszy fokus review (nie ma noise z innych plików)
- ✅ **Dwustopniowa architektura**:
  * Pomocniczy LLM (tańszy - GPT-4o-mini): parsing + filtrowanie
  * Główny LLM (droższy - GPT-4o): review + interpretacja
  * Optymalizacja kosztów (większość pracy w tanim modelu)
- ✅ **Inteligentna interpretacja** - główny LLM może:
  * Wyjaśnić WHY issue jest problemem
  * Dodać kontekst biznesowy i architektoniczny
  * Wykryć false positives
  * Znaleźć powiązane problemy nie wykryte przez CI
  * Zasugerować konkretny fix z code example
  * Inne tylko tekstowy output per plik
  * Jeszcze inne tylko ogólne logi bez szczegółów
  * **LLM radzi sobie z wszystkimi** - interpretuje raw output bez sztywnego parsingu
  * Brak wymuszonej struktury = łatwiejsza integracja z dowolnym narzędziem

**Przykład flow**:
```
1. Developer tworzy PR → uruchamia GitHub Actions (Ruff, mypy, ESLint)
2. ACR webhook otrzymuje pull_request.opened
3. ReviewOrchestrator.conduct_review():
   a. _build_context():
      • RAG retrieval + architectural docs + rules from config
   b. _fetch_ci_results():
      - Wait for CI completion (max 300s)
      - GitHubChecksAdapter.fetch_ci_results()
      - GET /check-runs → filter by "Ruff", "mypy", "ESLint"
      - Próba GET /check-runs/{id}/annotations (structured)
      - Fallback: GET logs/output (raw text)
      - Result: [CIToolResult(tool_name="Ruff", raw_output="main.py:42: F401 Unused import...")]
   c. **_parse_ci_results_with_llm()** (pomocniczy LLM - GPT-4o-mini):
      - Prompt: "Parse these CI outputs for changed files: [main.py:1-50, utils.py:1-30]"
      - LLM parsuje raw outputs (różne formaty: JSON, text, logs)
      - LLM zwraca structured JSON:
        ```json
        {"issues": [
          {"tool_name": "Ruff", "file_path": "main.py", "line_number": 42, 
           "severity": "error", "issue_code": "F401", 
           "message": "Unused import: typing.Optional",
           "suggestion": "Remove unused import", "is_in_diff": true}
        ]}
        ```
      - Result: [ParsedCIIssue(...)] - tylko issues w changed files
   d. Dodaje parsed_ci_issues do context.parsed_ci_issues
   e. LLM generation (główny LLM - GPT-4o):
      • Prompt zawiera sekcję "Static Analysis Issues (Parsed from CI/CD)"
      • LLM widzi: "[ERROR] Ruff (F401): Unused import: typing.Optional at main.py:42"
      • LLM interpretuje i generuje komentarz:
        "Line 42: Remove unused import `typing.Optional`. This is never used in the code.
         Ruff (F401) detected this. Consider using `from __future__ import annotations`
         if you need forward references."
   f. Publikacja komentarzy
4. Developer widzi komentarze z kontekstem i wyjaśnieniem (nie tylko raw CI output)
```

**Przykład komentarza LLM bazującego na CI result**:
```
❌ **ERROR** (LLM)
Line 42: Unused import detected

Ruff found an unused import of `typing.Optional` on this line. This import is never 
used in the file and should be removed to keep the code clean.

**Suggested fix:**
```python
# Remove line 42:
- from typing import Optional
```

If you need forward references, consider using:
```python
from __future__ import annotations
```

This is a common issue when refactoring - you may have removed the code that used this import.
```

### Dwustopniowy proces LLM dla CI results

**Problem**: Raw CI outputs w różnych formatach (JSON, text, logs) są trudne do bezpośredniego wykorzystania przez główny LLM:
- Duże prompty (całe raw outputs) → wysokie koszty
- Noise (issues w niezmienioych plikach) → gorszy fokus review
- Różnorodność formatów → trudność w konsumpcji

**Rozwiązanie - dwustopniowa architektura LLM**:

**Krok 1: Pomocniczy LLM (Parsing & Filtering)**
- Model: GPT-4o-mini lub Claude-3-Haiku (tańszy, szybszy)
- Input: Raw CI outputs (wszystkie formaty) + changed files/lines
- Zadanie:
  * Parse różne formaty (JSON, text, logs)
  * Extract structured issues: {file, line, severity, code, message}
  * Filter tylko issues w changed files
  * Oznacz is_in_diff (czy w zmienionych liniach)
  * Opcjonalnie: dodaj wstępną suggestion
- Output: List[ParsedCIIssue] - clean, structured, filtered
- Koszt: ~$0.0001 per 1K tokens (GPT-4o-mini)

**Krok 2: Główny LLM (Review & Interpretation)**
- Model: GPT-4o lub Claude-3.5-Sonnet (główny review)
- Input: PR diff + context (RAG, rules) + **ParsedCIIssue[]** (clean)
- Zadanie:
  * Review kodu (główne zadanie)
  * Interpretuj ParsedCIIssues w kontekście PR
  * Wyjaśnij WHY, dodaj context, sugeruj fix
  * Wykryj false positives
  * Znajdź powiązane problemy
- Output: ReviewComment[]
- Koszt: ~$0.005 per 1K tokens (GPT-4o)

**Korzyści**:
- ✅ **Optymalizacja kosztów**: ciężka praca (parsing) w tanim modelu
- ✅ **Mniejsze prompty**: główny LLM dostaje filtered issues, nie raw outputs
- ✅ **Lepszy fokus**: tylko relevant issues w changed files
- ✅ **Elastyczność**: pomocniczy LLM radzi sobie z dowolnym formatem
- ✅ **Rozdzielenie concerns**: parsing vs review logic
- ✅ **Skalowalność**: parsing może być cache'owany per CI run

**Przykład flow**:
```
1. CI runs: Ruff, mypy, ESLint → różne formaty (JSON, text, logs)
2. ACR fetches raw outputs: 
   - CIToolResult(tool="Ruff", raw_output="src/main.py:42: F401...")
   - CIToolResult(tool="mypy", raw_output="src/utils.py:15: error: Incompatible...")
   
3. Pomocniczy LLM (GPT-4o-mini):
   Input: "Parse these outputs for changed files: [main.py:1-50, utils.py:1-30]"
   Output: [
     ParsedCIIssue(file="main.py", line=42, code="F401", message="Unused import", is_in_diff=True),
     ParsedCIIssue(file="utils.py", line=15, severity="error", message="Type mismatch", is_in_diff=False)
   ]
   Cost: $0.0001
   
4. Główny LLM (GPT-4o):
   Input: Diff + Context + ParsedCIIssues (2 clean, structured issues)
   Output: [
     ReviewComment(line=42, text="Remove unused import. Ruff detected this..."),
     ReviewComment(line=25, text="Consider adding type hints for better clarity...")
   ]
   Cost: $0.005
```

**Optymalizacja**: Pomocniczy LLM może być wywołany **raz per CI run** i cache'owany (ParsedCIIssues as artifact).

### Tree-sitter AST parsing dla context enhancement

**Problem**: Diff pokazuje tylko fragmenty kodu - LLM nie widzi pełnego kontekstu funkcji.

**Rozwiązanie - Tree-sitter AST parsing**:
- Ekstrakcja pełnych funkcji ze zmienionych plików (nie tylko diff fragments)
- Budowa call graph (dependencies między funkcjami)
- Augmentacja kontekstu RAG o strukturalną wiedzę o kodzie

**Integracja w systemie**:

**1. Ekstrakcja funkcji (podczas _build_context)**:
```python
# ReviewOrchestrator._extract_functions_from_diff()
for hunk in pr.diff_hunks:
    full_code = vcs.fetch_file(repo, hunk.file_path, branch)
    functions = ast_parser.extract_changed_functions(hunk, full_code, language)
    # Zwraca: List[FunctionNode] - tylko funkcje z changami
```

**2. Augmentacja CodeContext**:
```python
CodeContext(
    documentation_chunks=[...],  # RAG retrieval (FAISS top-5)
    historical_reviews=[...],
    general_rules=[...],
    parsed_ci_issues=[...],      # Parsed przez helper LLM
    extracted_functions=[        # Tree-sitter AST
        FunctionNode(
            name="calculate_discount",
            start_line=42,
            end_line=58,
            body="def calculate_discount(price, rate):\n    ...",
            language=Language.PYTHON
        )
    ]
)
```

**3. Serializacja do promptu** (`to_prompt_context()`):
```
# Extracted Functions from Changed Files (AST)

The following functions were extracted from changed files using AST parsing.
Use this to understand the full context of changed code, not just diff fragments.

### Function: calculate_discount (lines 42-58)
```python
def calculate_discount(price, rate):
    if rate < 0 or rate > 1:
        raise ValueError("Rate must be between 0 and 1")
    return price * (1 - rate)
```

### Function: apply_coupon (lines 60-75)
```python
def apply_coupon(order, coupon_code):
    discount_rate = get_discount_rate(coupon_code)
    order.total = calculate_discount(order.total, discount_rate)
    return order
```
```

**Korzyści**:
- ✅ **Pełny kontekst**: LLM widzi całe funkcje, nie tylko zmienione linie
- ✅ **Call graph awareness**: TreeSitterParser.build_call_graph() wykrywa dependencies
- ✅ **Izolacja funkcji**: Tylko funkcje z changami (nie cały plik)
- ✅ **Multi-language**: Python, JavaScript, TypeScript, Go, Java
- ✅ **Literatura-backed**: Meng2025RARe (RAG top-5), Pornprasit2024 (Tree-sitter), Ren2025HydraReviewer (call graph)

**Przykład użycia w review**:
```
Diff pokazuje:
  - return price * rate
  + return price * (1 - rate)

LLM widzi pełną funkcję calculate_discount() (linie 42-58) i rozumie:
- Logika biznesowa: obliczanie zniżki
- Walidacja: rate must be 0-1
- Kontekst: używana w apply_coupon()
→ Komentarz: "Good fix! Previously calculated markup, not discount. Consider adding unit test for edge case rate=0."
```

**Optymalizacja**: Limit top-5 największych funkcji (zapobiega context overflow).

### Dynamiczne standardy kodowania z konfiguracji

**Problem**: Hardcodowanie standardów kodowania w systemie uniemożliwia dostosowanie do specyfiki projektu.

**Rozwiązanie - konfiguracja w `.acr-config.yml`**:
- Wszystkie standardy kodowania definiowane per-projekt
- Konwencje nazewnictwa per-język
- Reguły biznesowe specyficzne dla domeny
- Kontekst RAG wzbogacony o te standardy automatycznie

**Korzyści**:
- Jeden system obsługuje różnorodne projekty
- Zespoły definiują własne reguły bez modyfikacji kodu ACR
- LLM otrzymuje precyzyjny kontekst projektu
- Łatwa aktualizacja standardów (edycja YAML, nie deployment kodu)

**Przykład flow**:
```
1. PR created → webhook
2. YAMLConfigLoader.get_config(repo) → wczytuje .acr-config.yml
3. ContextBuilder.load_standards_from_config(config) → wyciąga:
   - coding_standards (PEP8, Airbnb JS Guide, itp.)
   - naming_conventions (snake_case, camelCase)
   - business_rules (auth required, SQL injection prevention)
4. LLM prompt enrichment:
   ## Coding Standards
   - Python max_line_length: 88
   - JavaScript style_guide: Airbnb
   
   ## Naming Conventions
   - Python functions: snake_case
   - JavaScript classes: PascalCase
   
   ## Business Rules
   - All API endpoints require authentication
   - SQL queries must use parameterized statements
5. LLM generuje komentarze zgodne z projektowymi standardami
```

### Zgodność z zasadami Clean Architecture

- **Warstwa Domain**: czysta logika biznesowa (ReviewOrchestrator, encje)
- **Warstwa Application**: use cases orkiestrujące flow (ProcessPullRequest)
- **Warstwa Infrastructure**: adaptery I/O (GitHub, OpenAI, FAISS)
- **Warstwa Presentation**: entry points (API, CLI)
- **Dependency Rule**: zależności skierowane do wewnątrz (Infrastructure → Domain)

### Zgodność z Clean Code

- **Meaningful names**: PullRequest, ReviewComment, CodeContext
- **Single Responsibility**: każda klasa ma jedną odpowiedzialność
- **DRY**: wspólne komponenty w `shared/`
- **Type hints**: pełna typizacja (mypy validation)
- **Docstrings**: dokumentacja publicznych API

### Zgodność z Open/Closed Principle (SOLID)

**Definicja**: "Klasy powinny być otwarte na rozszerzenia, ale zamknięte na modyfikacje."

System implementuje OCP w dwóch kluczowych obszarach:

#### 1. LLM Providers (Factory Pattern)

**Problem przed OCP**:
```python
# Container.resolve(LLMProvider) - PRZED ❌
if config["llm"]["provider"] == "openai":
    instance = OpenAIAdapter(...)
elif config["llm"]["provider"] == "anthropic":
    instance = AnthropicAdapter(...)
elif config["llm"]["provider"] == "gemini":  # ❌ Modyfikacja Container!
    instance = GeminiAdapter(...)
```

**Rozwiązanie z OCP**:
```python
# LLMProviderFactory - PO ✅
LLMProviderFactory.register("openai", OpenAIAdapter)
LLMProviderFactory.register("anthropic", AnthropicAdapter)
LLMProviderFactory.register("gemini", GeminiAdapter)  # ✅ Tylko rejestracja!

# Container
instance = LLMProviderFactory.create(provider_name, **kwargs)
```

**Dodanie nowego providera (Google Gemini)**:
```python
# 1. Nowy plik: adapters/llm/gemini_adapter.py
class GeminiAdapter(LLMProvider):
    def generate_review(...): ...
    def parse_ci_output(...): ...
    def estimate_cost(...): ...

# 2. Rejestracja (auto-import lub explicit)
LLMProviderFactory.register("gemini", GeminiAdapter)

# 3. Użycie (bez zmian w Container!)
# .acr-config.yml: llm.provider = "gemini"
# Container automatycznie używa factory
```

**Korzyści**:
- ✅ Dodanie Gemini = tylko 1 nowy plik (`gemini_adapter.py`)
- ✅ **Brak modyfikacji**: `Container` (300 linii), `OpenAIAdapter` (200 linii), `ReviewOrchestrator` (500 linii)
- ✅ Type safety: `Type[LLMProvider]` wymusza interface compliance
- ✅ Testowanie: Mock factory w unit testach
- ✅ Runtime discovery: `LLMProviderFactory.list_providers()`

#### 2. Tree-sitter Languages (Strategy + Registry Pattern)

**Problem przed OCP**:
```python
# TreeSitterParser - PRZED ❌
def _get_function_query(self, language: Language):
    queries = {
        Language.PYTHON: "(function_definition) @function",
        Language.JAVASCRIPT: "(function_declaration) @function",
        # ...
        Language.RUST: "(function_item) @function"  # ❌ Modyfikacja TreeSitterParser!
    }
    return queries[language]

def extract_function_name(self, node):
    if language == Language.PYTHON:  # ❌ if/elif hell
        # ...
    elif language == Language.RUST:  # ❌ Nowy if branch!
        # ...
```

**Rozwiązanie z OCP**:
```python
# LanguageStrategy - PO ✅
class LanguageStrategy(ABC):
    @abstractmethod
    def get_function_query(self) -> str: ...
    @abstractmethod
    def extract_function_name(self, node) -> str: ...

class PythonLanguageStrategy(LanguageStrategy):
    def get_function_query(self) -> str:
        return "(function_definition) @function"
    def extract_function_name(self, node) -> str:
        # Python-specific logic

# Registry
LanguageRegistry.register(Language.PYTHON, PythonLanguageStrategy())
LanguageRegistry.register(Language.RUST, RustLanguageStrategy())  # ✅ Tylko rejestracja!

# TreeSitterParser używa registry (bez zmian!)
strategy = LanguageRegistry.get(language)
query = strategy.get_function_query()
```

**Dodanie nowego języka (Rust)**:
```python
# 1. Dodaj enum value
class Language(Enum):
    # ... existing ...
    RUST = "rust"

# 2. Nowy plik: ast/strategies/rust_strategy.py
class RustLanguageStrategy(LanguageStrategy):
    def get_function_query(self) -> str:
        return "(function_item) @function"
    
    def get_call_expression_query(self) -> str:
        return "(call_expression (identifier) @call)"
    
    def extract_function_name(self, node) -> str:
        for child in node.children:
            if child.type == "identifier":
                return child.text.decode("utf8")
        return "<anonymous>"
    
    def get_parser_name(self) -> str:
        return "rust"

# 3. Rejestracja
LanguageRegistry.register(Language.RUST, RustLanguageStrategy())

# 4. That's it! TreeSitterParser automatycznie obsługuje Rust
```

**Korzyści**:
- ✅ Dodanie Rust = tylko 1 nowy plik (`rust_strategy.py`)
- ✅ **Brak modyfikacji**: `TreeSitterParser` (150 linii), testy (300 linii)
- ✅ Izolacja: Rust logic tylko w `RustLanguageStrategy`
- ✅ Single Responsibility: 1 strategy = 1 język
- ✅ Testowanie: Unit test tylko Rust strategy (nie cały parser)

#### Porównanie: przed vs po OCP

| Aspekt | Przed OCP | Po OCP |
|--------|-----------|--------|
| **Dodanie Gemini** | Edycja `Container.resolve()` (300 linii) | Nowy plik `gemini_adapter.py` |
| **Dodanie Rust** | Edycja `TreeSitterParser` (150 linii) | Nowy plik `rust_strategy.py` |
| **Regresja risk** | Wysoki (modyfikacja core logic) | Brak (core niezmienione) |
| **Test coverage** | Re-test całego `Container` | Test tylko nowego adaptera |
| **Merge conflicts** | Wysokie (shared files) | Brak (separate files) |
| **Onboarding** | "Where to add?" (code diving) | "Register in factory" (clear) |

#### Implementacja w systemie

**Auto-registration pattern**:
```python
# adapters/llm/__init__.py
from .openai_adapter import OpenAIAdapter
from .anthropic_adapter import AnthropicAdapter

def register_llm_providers():
    LLMProviderFactory.register("openai", OpenAIAdapter)
    LLMProviderFactory.register("anthropic", AnthropicAdapter)

register_llm_providers()  # Called on import

# ast/strategies/__init__.py
from .python_strategy import PythonLanguageStrategy
from .javascript_strategy import JavaScriptLanguageStrategy
# ...

def register_language_strategies():
    LanguageRegistry.register(Language.PYTHON, PythonLanguageStrategy())
    LanguageRegistry.register(Language.JAVASCRIPT, JavaScriptLanguageStrategy())
    # ...

register_language_strategies()
```

**Plugin system gotowość**:
```python
# Przyszłość: dynamiczne ładowanie z external plugins
import importlib

def load_plugin(plugin_name: str):
    module = importlib.import_module(f"acr_plugins.{plugin_name}")
    # Plugin auto-registers przez factory/registry
    
# .acr-config.yml
plugins:
  - gemini_provider
  - rust_language
```

---

## Deployment (CI/CD)

### Docker Compose

```yaml
# docker-compose.yml

version: '3.8'

services:
  acr-api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - GITHUB_TOKEN=${GITHUB_TOKEN}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/acr
    depends_on:
      - db
      - redis
    volumes:
      - ./.acr_index:/app/.acr_index
  
  db:
    image: postgres:15
    environment:
      - POSTGRES_DB=acr
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
  
  redis:
    image: redis:7
    ports:
      - "6379:6379"
```

### Integracja z istniejącym CI/CD

ACR integruje się z projektowymi pipeline'ami CI/CD poprzez:
1. **Webhook** - GitHub/GitLab wywołuje ACR przy zdarzeniu `pull_request.opened`
2. **Checks API** - ACR pobiera wyniki z istniejących kroków CI (Ruff, mypy, ESLint)
3. **Publikacja komentarzy** - ACR dodaje komentarze LLM + CI do PR

**Przykład: Projekt z istniejącym CI**

```yaml
# .github/workflows/ci.yml (ISTNIEJĄCY pipeline projektu)

name: CI

on:
  pull_request:
  push:
    branches: [main]

jobs:
  lint-python:
    name: Ruff
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install ruff
      - run: ruff check . --output-format=github  # ✨ GitHub annotations
  
  type-check:
    name: mypy
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
      - run: pip install mypy
      - run: mypy . --show-column-numbers --show-error-codes  # ✨ GitHub annotations
  
  lint-typescript:
    name: ESLint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
      - run: npm ci
      - run: npm run lint  # ✨ ESLint annotations via @github/eslint-formatter
```

**ACR System - tylko webhook receiver (NIE jest krokiem CI)**

ACR działa jako **osobny serwis** który:
- Odbiera webhook z GitHub przy `pull_request.opened`
- **Czeka** na zakończenie CI (checks: Ruff, mypy, ESLint)
- **Pobiera** wyniki z GitHub Checks API
- Generuje dodatkowe komentarze LLM (z kontekstem RAG)
- Publikuje wszystkie komentarze do PR

```yaml
# Konfiguracja ACR w repozytorium projektu
# .acr-config.yml

project:
  name: "my-project"
  languages: [python, typescript]

review:
  # ... rule_sets, file_patterns ...

static_analysis:
  enabled: true
  
  # ✨ ACR pobiera wyniki z tych check-runs (NIE uruchamia ich)
  github_check_names:
    - "Ruff"        # Z job: lint-python
    - "mypy"        # Z job: type-check
    - "ESLint"      # Z job: lint-typescript
  
  ci_timeout: 300   # Max 5 minut wait na CI
```

**Flow wykonania**:
```
1. Developer tworzy PR
   ↓
2. GitHub uruchamia workflow ci.yml (Ruff, mypy, ESLint)
   + GitHub wysyła webhook do ACR System
   ↓
3. ACR System (webhook receiver):
   a. Odbiera webhook pull_request.opened
   b. Czeka na zakończenie CI checks (is_ci_completed → wait max 300s)
   c. Pobiera wyniki: GET /check-runs, GET /annotations
   d. Generuje komentarze LLM (GPT-4o + RAG)
   e. Merge CI issues + LLM comments
   f. POST /pulls/{pr}/reviews (publikacja inline comments)
   ↓
4. Developer widzi w PR:
   - Annotations z CI (Ruff, mypy, ESLint) - jako check failures
   - Komentarze ACR (LLM + CI merged) - jako review comments
```

**Deployment ACR System**:
```yaml
# docker-compose.yml (ACR jako osobny serwis)

version: '3.8'

services:
  acr-api:
    build: .
    ports:
      - "8000:8000"  # Webhook receiver
    environment:
      - GITHUB_TOKEN=${GITHUB_TOKEN}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    restart: always
```

**Rejestracja webhooka w GitHub** (ręcznie lub via GitHub App):
```
URL: https://acr.yourcompany.com/webhooks/github
Events: pull_request (opened, synchronize)
Secret: ${WEBHOOK_SECRET}
```

---

## Roadmap rozwoju

1. **Faza 1: MVP (GitHub + OpenAI + FAISS)**
   - Integracja GitHub (webhook + REST API + paginacja)
   - RAG z FAISS (dokumentacja + historical reviews)
   - Generacja komentarzy GPT-4o
   - Publikacja inline comments
   - Podstawowa obsługa `.acr-config.yml` (coding_standards, naming_conventions, business_rules)

2. **Faza 2: Skalowalność i konfigurowalność**
   - **Chunkowanie dużych PR** (automatyczne dzielenie na chunki po 500 linii)
   - Deduplikacja komentarzy w chunkach
   - **Dynamiczne standardy z konfiguracji** (per-projekt, per-język)
   - Model selection per language (z konfigu)
   - Cost tracking per chunk

3. **Faza 3: Rozszerzenie platform**
   - GitLab adapter (REST API + webhooks + paginacja)
   - Claude/Anthropic adapter
   - BitBucket adapter (opcjonalnie)

4. **Faza 4: Integracja z CI/CD**
   - **GitHubChecksAdapter** - fetch wyników z GitHub Checks API (Ruff, mypy, ESLint)
   - **GitLabCIAdapter** - fetch wyników z GitLab CI artifacts/logs
   - **CI results jako źródło kontekstu dla LLM** (nie jako osobne komentarze)
   - LLM interpretuje CI findings: potwierdza, wyjaśnia, sugeruje fixy, wykrywa false positives
   - Wait for CI completion z konfiguowalnym timeout
   - Human-in-the-loop trigger (configurable threshold)

5. **Faza 5: Ewaluacja i metryki**
   - BLEU-4, BERTScore calculation
   - Human evaluation framework (praktycy)
   - Cost tracking dashboard (per-PR, per-chunk, per-repo)
   - Regression ratio tracking (test failures caused by suggestions)

6. **Faza 6: Produkcja i optymalizacja**
   - Caching (Redis) dla RAG retrieval i config
   - Rate limiting (API calls per repo)
   - Multi-tenancy (izolacja per organization)
   - Observability (Prometheus, Grafana)
   - Parallel chunk processing (async)
   - Webhook retry mechanism
