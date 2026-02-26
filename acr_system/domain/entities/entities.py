"""Domain entities for the ACR system."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from uuid import UUID, uuid4

from acr_system.domain.value_objects.value_objects import FilePath, Language, Severity


@dataclass
class DiffHunk:
    """Fragment of code change in a file."""
    
    id: UUID = field(default_factory=uuid4)
    file_path: FilePath
    old_start_line: int
    old_line_count: int
    new_start_line: int
    new_line_count: int
    content: str  # Raw diff content
    context_before: str = ""  # Code context before the hunk
    context_after: str = ""  # Code context after the hunk
    
    def __post_init__(self) -> None:
        if self.old_start_line < 0:
            raise ValueError("old_start_line cannot be negative")
        if self.new_start_line < 0:
            raise ValueError("new_start_line cannot be negative")
        if not self.content:
            raise ValueError("Diff content cannot be empty")
    
    @property
    def language(self) -> Language:
        """Get programming language from file extension."""
        return Language.from_extension(self.file_path.extension)
    
    def is_line_in_hunk(self, line_number: int) -> bool:
        """Check if a line number is within this hunk's new lines."""
        return self.new_start_line <= line_number < (self.new_start_line + self.new_line_count)


@dataclass
class ReviewComment:
    """Code review comment."""
    
    id: UUID = field(default_factory=uuid4)
    file_path: FilePath
    line_number: Optional[int]
    severity: Severity
    message: str
    suggestion: Optional[str] = None
    rule_name: Optional[str] = None  # Which rule triggered this comment
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def __post_init__(self) -> None:
        if not self.message:
            raise ValueError("Comment message cannot be empty")
        if self.line_number is not None and self.line_number < 1:
            raise ValueError("Line number must be positive")


@dataclass
class ParsedCIIssue:
    """
    CI issue parsed by LLM - extracted from raw output, only relevant for diff.
    LLM parsing step: filters issues to changed files/lines.
    """
    
    tool_name: str  # "Ruff", "mypy", "ESLint"
    file_path: str  # "src/main.py"
    line_number: Optional[int]  # 42 (or None if general issue)
    severity: str  # "error", "warning", "info"
    issue_code: Optional[str]  # "F401", "E501", "prefer-const"
    message: str  # "Unused import: typing.Optional"
    suggestion: Optional[str] = None  # Optional fix suggestion from parsing LLM
    
    def __post_init__(self) -> None:
        if not self.tool_name:
            raise ValueError("tool_name cannot be empty")
        if not self.file_path:
            raise ValueError("file_path cannot be empty")
        if not self.message:
            raise ValueError("message cannot be empty")
    
    def to_review_comment(self) -> ReviewComment:
        """Convert CI issue to review comment."""
        severity_map = {
            "error": Severity.ERROR,
            "warning": Severity.WARNING,
            "info": Severity.INFO,
        }
        
        severity_obj = Severity(level=severity_map.get(self.severity, Severity.INFO))
        
        message = f"[{self.tool_name}] {self.message}"
        if self.issue_code:
            message = f"[{self.tool_name}:{self.issue_code}] {self.message}"
        
        return ReviewComment(
            file_path=FilePath(self.file_path),
            line_number=self.line_number,
            severity=severity_obj,
            message=message,
            suggestion=self.suggestion,
            rule_name=self.tool_name,
        )


@dataclass
class CIToolResult:
    """
    Loosely collected results from one CI tool (Ruff, mypy, ESLint).
    Different tools = different formats. Raw output - requires parsing by LLM.
    """
    
    tool_name: str  # "Ruff", "mypy", "ESLint", "pytest"
    status: str  # "success", "failure", "warning"
    raw_output: str  # Full output from tool (text or JSON)
    files_mentioned: set[str]  # Files mentioned in output (best effort parsing)
    conclusion: str  # "passed", "failed", "skipped"
    
    def __post_init__(self) -> None:
        if not self.tool_name:
            raise ValueError("tool_name cannot be empty")
        if not self.status:
            raise ValueError("status cannot be empty")


@dataclass
class CodeContext:
    """Code context for RAG retrieval."""
    
    content: str
    source: str  # "documentation", "architecture", "previous_review"
    file_path: Optional[FilePath] = None
    relevance_score: float = 0.0
    
    def __post_init__(self) -> None:
        if not self.content:
            raise ValueError("Context content cannot be empty")
        if not self.source:
            raise ValueError("Context source cannot be empty")
        if not 0 <= self.relevance_score <= 1:
            raise ValueError("Relevance score must be between 0 and 1")


@dataclass
class ArchitecturalDocument:
    """Architectural document from repository (ARCHITECTURE.md, ADR/*.md)."""
    
    filename: str
    content: str
    last_modified: datetime
    
    def __post_init__(self) -> None:
        if not self.filename:
            raise ValueError("filename cannot be empty")
        if not self.content:
            raise ValueError("content cannot be empty")


@dataclass
class PullRequest:
    """Pull Request / Merge Request entity."""
    
    id: UUID = field(default_factory=uuid4)
    pr_number: int
    repository: str  # "owner/repo"
    title: str
    description: str
    author: str
    source_branch: str
    target_branch: str
    diff_hunks: list[DiffHunk] = field(default_factory=list)
    ci_results: list[CIToolResult] = field(default_factory=list)
    review_comments: list[ReviewComment] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def __post_init__(self) -> None:
        if self.pr_number < 1:
            raise ValueError("PR number must be positive")
        if not self.repository:
            raise ValueError("Repository cannot be empty")
        if not self.title:
            raise ValueError("PR title cannot be empty")
    
    def add_diff_hunk(self, hunk: DiffHunk) -> None:
        """Add a diff hunk to the PR."""
        self.diff_hunks.append(hunk)
    
    def add_ci_result(self, result: CIToolResult) -> None:
        """Add CI result to the PR."""
        self.ci_results.append(result)
    
    def add_review_comment(self, comment: ReviewComment) -> None:
        """Add review comment to the PR."""
        self.review_comments.append(comment)
    
    @property
    def changed_files(self) -> set[str]:
        """Get set of all changed files."""
        return {hunk.file_path.value for hunk in self.diff_hunks}
    
    @property
    def languages(self) -> set[Language]:
        """Get set of all programming languages in the PR."""
        return {hunk.language for hunk in self.diff_hunks}
    
    def get_hunks_for_file(self, file_path: str) -> list[DiffHunk]:
        """Get all hunks for a specific file."""
        return [hunk for hunk in self.diff_hunks if hunk.file_path.value == file_path]


@dataclass
class FunctionNode:
    """Function extracted from AST (Tree-sitter).
    
    Represents a function/method with its metadata and body.
    Used for context enhancement in RAG and impact analysis.
    """
    
    name: str
    file_path: FilePath
    start_line: int
    end_line: int
    body: str  # Full function body code
    language: Language
    signature: Optional[str] = None  # Function signature (with params, return type)
    docstring: Optional[str] = None
    
    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Function name cannot be empty")
        if self.start_line < 1:
            raise ValueError("start_line must be positive")
        if self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line")
        if not self.body:
            raise ValueError("Function body cannot be empty")
    
    @property
    def line_count(self) -> int:
        """Number of lines in the function."""
        return self.end_line - self.start_line + 1
    
    def contains_line(self, line_number: int) -> bool:
        """Check if a line number is within this function."""
        return self.start_line <= line_number <= self.end_line
