"""Domain interfaces (Ports) for infrastructure adapters."""
from abc import ABC, abstractmethod
from typing import Optional

from acr_system.domain.entities.entities import (
    ArchitecturalDocument,
    CIToolResult,
    CodeContext,
    DiffHunk,
    ParsedCIIssue,
    PullRequest,
    ReviewComment,
)
from acr_system.domain.value_objects.value_objects import RAGConfig


class VCSRepository(ABC):
    """Port for VCS (GitHub/GitLab) operations."""
    
    @abstractmethod
    async def get_pull_request(self, repo: str, pr_number: int) -> PullRequest:
        """Fetch pull request details."""
        pass
    
    @abstractmethod
    async def get_diff_hunks(self, repo: str, pr_number: int) -> list[DiffHunk]:
        """Fetch diff hunks for a PR."""
        pass
    
    @abstractmethod
    async def post_review_comment(
        self,
        repo: str,
        pr_number: int,
        comment: ReviewComment,
    ) -> None:
        """Post a review comment to the PR."""
        pass
    
    @abstractmethod
    async def post_review_comments(
        self,
        repo: str,
        pr_number: int,
        comments: list[ReviewComment],
    ) -> None:
        """Post multiple review comments to the PR."""
        pass
    
    @abstractmethod
    async def get_file_content(
        self,
        repo: str,
        file_path: str,
        ref: str,
    ) -> str:
        """Get file content at a specific ref (branch/commit)."""
        pass


class LLMProvider(ABC):
    """Port for LLM provider (OpenAI/Anthropic)."""
    
    @abstractmethod
    async def generate_review_comments(
        self,
        diff_hunk: DiffHunk,
        rules_text: str,
        context: list[CodeContext],
        ci_issues: list[ParsedCIIssue],
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> list[ReviewComment]:
        """Generate review comments for a diff hunk."""
        pass
    
    @abstractmethod
    async def parse_ci_output(
        self,
        ci_result: CIToolResult,
        changed_files: set[str],
    ) -> list[ParsedCIIssue]:
        """Parse CI tool output and extract relevant issues."""
        pass
    
    @abstractmethod
    async def generate_completion(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> str:
        """Generate a completion for a prompt."""
        pass


class EmbeddingStore(ABC):
    """Port for vector database (FAISS/Pinecone)."""
    
    @abstractmethod
    async def index_documents(
        self,
        documents: list[ArchitecturalDocument],
    ) -> None:
        """Index documents for RAG retrieval."""
        pass
    
    @abstractmethod
    async def search_similar(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[dict[str, str]] = None,
    ) -> list[CodeContext]:
        """Search for similar code contexts."""
        pass
    
    @abstractmethod
    async def index_review_history(
        self,
        pr: PullRequest,
    ) -> None:
        """Index PR review for future RAG retrieval."""
        pass


class StaticAnalyzer(ABC):
    """Port for fetching CI/CD results (GitHub Checks/GitLab CI)."""
    
    @abstractmethod
    async def fetch_ci_results(
        self,
        repo: str,
        pr_number: int,
    ) -> list[CIToolResult]:
        """Fetch CI results for a PR."""
        pass
    
    @abstractmethod
    async def get_check_runs(
        self,
        repo: str,
        commit_sha: str,
    ) -> list[CIToolResult]:
        """Get check runs for a specific commit."""
        pass


class ConfigRepository(ABC):
    """Port for project configuration."""
    
    @abstractmethod
    async def load_config(self, repo: str, ref: str) -> "ProjectConfig":
        """Load project configuration from repository."""
        pass
    
    @abstractmethod
    async def get_rules_for_file(
        self,
        config: "ProjectConfig",
        file_path: str,
    ) -> tuple[str, Optional[RAGConfig]]:
        """Get applicable rules and RAG config for a file.
        
        Returns:
            Tuple of (rules_text, rag_config)
        """
        pass


# Forward reference for type hints
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from acr_system.infrastructure.config.project_config import ProjectConfig
