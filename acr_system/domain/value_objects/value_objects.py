"""Value objects for the Domain layer."""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


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
    documentation_paths: list[str] = None  # type: ignore
    architectural_docs: list[str] = None  # type: ignore
    
    def __post_init__(self) -> None:
        if self.documentation_paths is None:
            self.documentation_paths = []
        if self.architectural_docs is None:
            self.architectural_docs = []
        
        if self.top_k < 1:
            raise ValueError("top_k must be positive")
