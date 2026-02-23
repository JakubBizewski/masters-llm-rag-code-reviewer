"""Data Transfer Objects for the Application layer."""
from dataclasses import dataclass
from typing import Optional

from acr_system.domain.entities.entities import ReviewComment
from acr_system.domain.value_objects.value_objects import LLMConfig, RAGConfig


@dataclass
class PRReviewRequest:
    """Request to review a pull request."""
    
    repository: str  # "owner/repo"
    pr_number: int
    config_override: Optional[dict] = None  # Optional config override
    

@dataclass
class ReviewResult:
    """Result of a pull request review."""
    
    repository: str
    pr_number: int
    comments: list[ReviewComment]
    success: bool
    error_message: Optional[str] = None
    
    @property
    def comment_count(self) -> int:
        """Get total number of comments."""
        return len(self.comments)
    
    @property
    def error_count(self) -> int:
        """Get number of error-level comments."""
        return sum(1 for c in self.comments if c.severity.level == "error")
    
    @property
    def warning_count(self) -> int:
        """Get number of warning-level comments."""
        return sum(1 for c in self.comments if c.severity.level == "warning")
    
    @property
    def info_count(self) -> int:
        """Get number of info-level comments."""
        return sum(1 for c in self.comments if c.severity.level == "info")


@dataclass
class ContextRetrievalRequest:
    """Request to retrieve context for RAG."""
    
    query: str
    top_k: int = 5
    filters: Optional[dict[str, str]] = None


@dataclass
class ReviewPublishRequest:
    """Request to publish review comments."""
    
    repository: str
    pr_number: int
    comments: list[ReviewComment]
    mode: str = "comment"  # "comment" | "review" | "approve" | "request_changes"
