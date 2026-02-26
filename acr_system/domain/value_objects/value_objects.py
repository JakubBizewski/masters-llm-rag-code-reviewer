"""Value objects for the Domain layer."""
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class FilePath:
    """Value object representing a file path."""
    
    value: str
    
    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("File path cannot be empty")
    
    @property
    def extension(self) -> str:
        """Get file extension."""
        return Path(self.value).suffix
    
    @property
    def filename(self) -> str:
        """Get filename without path."""
        return Path(self.value).name
    
    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Language:
    """Value object representing programming language."""
    
    name: str
    
    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Language name cannot be empty")
        
        # Normalize to lowercase
        object.__setattr__(self, 'name', self.name.lower())
    
    @classmethod
    def from_extension(cls, extension: str) -> "Language":
        """Determine language from file extension."""
        extension_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".cs": "csharp",
            ".cpp": "cpp",
            ".c": "c",
            ".rb": "ruby",
            ".php": "php",
        }
        
        language_name = extension_map.get(extension.lower(), "unknown")
        return cls(name=language_name)
    
    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
class Severity:
    """Value object representing issue severity level."""
    
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    
    level: str
    
    def __post_init__(self) -> None:
        valid_levels = {self.ERROR, self.WARNING, self.INFO}
        if self.level not in valid_levels:
            raise ValueError(f"Invalid severity level: {self.level}. Must be one of {valid_levels}")
    
    @property
    def priority(self) -> int:
        """Get numeric priority (higher = more severe)."""
        priority_map = {
            self.ERROR: 3,
            self.WARNING: 2,
            self.INFO: 1,
        }
        return priority_map[self.level]
    
    def __str__(self) -> str:
        return self.level


@dataclass(frozen=True)
class CommentSource:
    """Value object representing the source of a review comment."""
    
    LLM = "llm"
    STATIC_ANALYSIS = "static_analysis"
    IMPACT_ANALYSIS = "impact_analysis"
    HUMAN = "human"
    
    source: str
    
    def __post_init__(self) -> None:
        valid_sources = {self.LLM, self.STATIC_ANALYSIS, self.IMPACT_ANALYSIS, self.HUMAN}
        if self.source not in valid_sources:
            raise ValueError(f"Invalid comment source: {self.source}. Must be one of {valid_sources}")
    
    def __str__(self) -> str:
        return self.source


@dataclass(frozen=True)
class RuleSet:
    """General set of code review rules (security, performance, quality)."""
    
    name: str
    enabled: bool
    rules_text: str  # LLM-friendly text, not rigid structure
    
    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("RuleSet name cannot be empty")
        if not self.rules_text:
            raise ValueError("RuleSet rules_text cannot be empty")


@dataclass
class FilePatternRule:
    """Rules for specific file patterns (glob)."""
    
    pattern: str  # Glob pattern: *.ts, */Domain/*.cs, **/*.test.ts
    rules_text: str  # LLM-friendly text
    priority: int = 0  # Higher value = higher priority (for conflicts)
    llm_config: Optional["LLMConfig"] = None  # Override global LLM settings
    rag_config: Optional["RAGConfig"] = None  # Override global RAG settings
    
    def __post_init__(self) -> None:
        if not self.pattern:
            raise ValueError("FilePatternRule pattern cannot be empty")
        if not self.rules_text:
            raise ValueError("FilePatternRule rules_text cannot be empty")


@dataclass
class LLMConfig:
    """LLM configuration (global or per file pattern)."""
    
    provider: str = "openai"  # openai | anthropic | custom
    model: str = "gpt-4o"
    temperature: float = 0.3
    max_tokens: int = 2000
    
    def __post_init__(self) -> None:
        if self.temperature < 0 or self.temperature > 2:
            raise ValueError("Temperature must be between 0 and 2")
        if self.max_tokens < 1:
            raise ValueError("max_tokens must be positive")


@dataclass
class RAGConfig:
    """RAG configuration (global or per file pattern)."""
    
    enabled: bool = True
    top_k: int = 5
    documentation_paths: Optional[List[str]] = None
    architectural_docs: Optional[List[str]] = None
    
    def __post_init__(self) -> None:
        if self.documentation_paths is None:
            self.documentation_paths = []
        if self.architectural_docs is None:
            self.architectural_docs = []
        
        if self.top_k < 1:
            raise ValueError("top_k must be positive")


@dataclass(frozen=True)
class ImpactAnalysisConfig:
    """Impact Analysis configuration for detecting breaking changes.
    
    Controls how the system analyzes the impact of code changes through
    call graph analysis and semantic understanding via LLM.
    """
    
    enabled: bool = True
    max_callers_per_function: int = 10  # Limit for performance
    depth: int = 1  # Only direct callers (not recursive)
    analyze_imports: bool = True  # Also analyze import dependencies
    severity_threshold: str = "medium"  # Publish only >= medium
    exclude_patterns: Tuple[str, ...] = ()  # Don't analyze these patterns
    
    def __post_init__(self) -> None:
        if self.max_callers_per_function < 1:
            raise ValueError("max_callers_per_function must be positive")
        if self.depth < 1:
            raise ValueError("depth must be positive")
        if self.severity_threshold not in {"low", "medium", "high", "critical"}:
            raise ValueError(f"Invalid severity_threshold: {self.severity_threshold}")


# ============================================================
# Impact Analysis Value Objects
# ============================================================


@dataclass(frozen=True)
class CallSite:
    """Value object representing a place where a function is called.
    
    Used in Impact Analysis to track who calls a changed function.
    Immutable to ensure consistency in dependency tracking.
    """
    
    file_path: FilePath
    line_number: int
    caller_name: str  # Name of the function/method that makes the call
    callee_name: str  # Name of the function/method being called
    context: str  # Code context around the call (5 lines window)
    
    def __post_init__(self) -> None:
        if self.line_number < 1:
            raise ValueError("Line number must be positive")
        if not self.caller_name:
            raise ValueError("caller_name cannot be empty")
        if not self.callee_name:
            raise ValueError("callee_name cannot be empty")
        if not self.context:
            raise ValueError("context cannot be empty")
    
    def __str__(self) -> str:
        return f"{self.file_path}:{self.line_number} - {self.caller_name}() calls {self.callee_name}()"


@dataclass(frozen=True)
class ImportSite:
    """Value object representing a place where a module/function is imported.
    
    Used in Impact Analysis to track who imports from a changed module.
    """
    
    file_path: FilePath
    line_number: int
    imported_module: str  # Name of imported module (e.g., "auth", "utils.helpers")
    imported_names: Tuple[str, ...]  # Imported names (functions, classes) - tuple for immutability
    context: str  # Import statement with surrounding context
    
    def __post_init__(self) -> None:
        if self.line_number < 1:
            raise ValueError("Line number must be positive")
        if not self.imported_module:
            raise ValueError("imported_module cannot be empty")
        if not self.imported_names:
            raise ValueError("imported_names cannot be empty")
        if not self.context:
            raise ValueError("context cannot be empty")
    
    def __str__(self) -> str:
        names = ", ".join(self.imported_names[:3])  # Show first 3 names
        if len(self.imported_names) > 3:
            names += ", ..."
        return f"{self.file_path}:{self.line_number} - imports {names} from {self.imported_module}"


@dataclass
class BreakingChange:
    """Represents a potential breaking change detected by Impact Analysis.
    
    Mutable to allow LLM to populate additional analysis fields.
    """
    
    caller_file: str  # Path to file with calling code
    caller_function: str  # Name of function that may break
    issue: str  # Description of what can break
    suggested_fix: str  # How to fix the calling code
    severity: Severity  # How critical is this breaking change
    
    def __post_init__(self) -> None:
        if not self.caller_file:
            raise ValueError("caller_file cannot be empty")
        if not self.caller_function:
            raise ValueError("caller_function cannot be empty")
        if not self.issue:
            raise ValueError("issue cannot be empty")
        if not self.suggested_fix:
            raise ValueError("suggested_fix cannot be empty")


@dataclass
class ImpactAnalysisResult:
    """Result of impact analysis for a changed function.
    
    Contains all callers, importers, and LLM analysis of potential breaking changes.
    Mutable to allow incremental population during analysis.
    """
    
    function_name: str
    file_path: FilePath
    callers: List[CallSite]
    importers: List[ImportSite]
    breaking_changes: List[BreakingChange]
    summary: str  # Overall assessment from LLM
    analysis_duration_ms: int = 0  # Performance tracking
    
    def __post_init__(self) -> None:
        if not self.function_name:
            raise ValueError("function_name cannot be empty")
        if not self.summary:
            raise ValueError("summary cannot be empty")
        if self.analysis_duration_ms < 0:
            raise ValueError("analysis_duration_ms cannot be negative")
    
    @property
    def has_breaking_changes(self) -> bool:
        """Check if any breaking changes were detected."""
        return len(self.breaking_changes) > 0
    
    @property
    def max_severity(self) -> Optional[Severity]:
        """Get the maximum severity of detected breaking changes."""
        if not self.breaking_changes:
            return None
        return max((bc.severity for bc in self.breaking_changes), key=lambda s: s.priority)
    
    @property
    def total_affected_sites(self) -> int:
        """Total number of affected call sites and import sites."""
        return len(self.callers) + len(self.importers)
    
    def get_critical_changes(self) -> List[BreakingChange]:
        """Get only critical breaking changes."""
        return [bc for bc in self.breaking_changes if bc.severity.level == Severity.ERROR]
