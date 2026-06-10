"""Data Transfer Objects for the Application layer."""
from dataclasses import dataclass
from typing import Dict, List, Optional

from acr_system.domain.entities.entities import ReviewComment
from acr_system.domain.value_objects.value_objects import LLMConfig, RAGConfig


@dataclass
class PRReviewRequest:
    """Request to review a pull request."""

    repository: str  # "owner/repo"
    pr_number: int
    config_override: Optional[dict] = None  # Optional config override
    # When set, review uses these exact refs instead of the current PR head.
    # head_sha — the commit to review (e.g. initial PR commit, not post-fixup)
    # base_sha — the merge-base to diff against
    head_sha: Optional[str] = None
    base_sha: Optional[str] = None
    

@dataclass
class ReviewResult:
    """Result of a pull request review."""
    
    repository: str
    pr_number: int
    comments: List[ReviewComment]
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
    filters: Optional[Dict[str, str]] = None


@dataclass
class ReviewPublishRequest:
    """Request to publish review comments."""
    
    repository: str
    pr_number: int
    comments: List[ReviewComment]
    mode: str = "comment"  # "comment" | "review" | "approve" | "request_changes"


@dataclass
class PRHistoryIndexRequest:
    """Request to index historical merged PRs for a repository."""

    repository: str  # "owner/repo"
    max_prs: int = 50


@dataclass
class PRHistoryIndexResult:
    """Result of indexing PR history."""

    repository: str
    indexed_count: int
    skipped_count: int
    success: bool
    error_message: Optional[str] = None
