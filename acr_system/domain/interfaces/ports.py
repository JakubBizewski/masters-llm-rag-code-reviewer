"""Domain interfaces (Ports) for infrastructure adapters."""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set, Tuple

from acr_system.domain.entities.entities import (
    ArchitecturalDocument,
    CIToolResult,
    CodeContext,
    DiffHunk,
    FunctionNode,
    ParsedCIIssue,
    PullRequest,
    PullRequestDiscussionComment,
    ReviewComment,
)
from acr_system.domain.value_objects.value_objects import (
    CallSite,
    FilePath,
    ImpactAnalysisResult,
    ImportSite,
    Language,
    RAGConfig,
)


class VCSRepository(ABC):
    """Port for VCS (GitHub/GitLab) operations."""
    
    @abstractmethod
    async def get_pull_request(self, repo: str, pr_number: int) -> PullRequest:
        """Fetch pull request details."""
        pass
    
    @abstractmethod
    async def get_diff_hunks(
        self,
        repo: str,
        pr_number: int,
        head_sha: Optional[str] = None,
        base_sha: Optional[str] = None,
    ) -> List[DiffHunk]:
        """Fetch diff hunks for a PR.

        If head_sha and base_sha are provided, the diff is computed between
        those two exact commits (base_sha...head_sha) instead of using the
        PR's current head. Use this to review the code as it was when the
        PR was first opened, before any fixup commits.
        """
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
        comments: List[ReviewComment],
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

    @abstractmethod
    async def list_merged_pull_requests(
        self,
        repo: str,
        limit: int = 50,
    ) -> List[int]:
        """List merged pull requests (most recent first).

        Returns a list of PR numbers.
        """
        pass

    @abstractmethod
    async def get_pull_request_discussion_comments(
        self,
        repo: str,
        pr_number: int,
    ) -> List[PullRequestDiscussionComment]:
        """Fetch PR discussion comments (review comments + issue comments).

        Returned comments should include replies (threading info) when available.
        """
        pass

    @abstractmethod
    async def get_pr_commits(
        self,
        repo: str,
        pr_number: int,
    ) -> List[Dict[str, Any]]:
        """Return commits belonging to the PR in chronological order.

        Each entry: {"sha": str, "committed_at": datetime}
        """
        pass

    @abstractmethod
    async def get_merge_base_sha(
        self,
        repo: str,
        base_ref: str,
        head_sha: str,
    ) -> Optional[str]:
        """Return the merge-base commit SHA between base_ref and head_sha.

        Equivalent to: git merge-base base_ref head_sha
        Returns None if the VCS backend does not support this operation.
        """
        pass


class LLMProvider(ABC):
    """Port for LLM provider (OpenAI/Anthropic)."""
    
    @abstractmethod
    async def generate_review_comments(
        self,
        diff_hunk: DiffHunk,
        rules_text: str,
        context: List[CodeContext],
        ci_issues: List[ParsedCIIssue],
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> List[ReviewComment]:
        """Generate review comments for a diff hunk."""
        pass
    
    @abstractmethod
    async def parse_ci_output(
        self,
        ci_result: CIToolResult,
        changed_files: Set[str],
    ) -> List[ParsedCIIssue]:
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
        documents: List[ArchitecturalDocument],
    ) -> None:
        """Index documents for RAG retrieval."""
        pass
    
    @abstractmethod
    async def search_similar(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, str]] = None,
    ) -> List[CodeContext]:
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
    ) -> List[CIToolResult]:
        """Fetch CI results for a PR."""
        pass
    
    @abstractmethod
    async def get_check_runs(
        self,
        repo: str,
        commit_sha: str,
    ) -> List[CIToolResult]:
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
    ) -> Tuple[str, Optional[RAGConfig], "LLMConfig"]:
        """Get applicable rules, RAG config, and LLM config for a file.
        
        Returns:
            Tuple of (rules_text, rag_config, llm_config)
        """
        pass


class CallGraphAnalyzer(ABC):
    """Port for technical dependency discovery (call tree, import tree).
    
    Pure static code analysis using grep + tree-sitter.
    Does NOT require LLM - only analyzes code structure.
    
    Use cases:
    - Find who calls a changed function
    - Find who imports from a changed module
    - Build dependency graphs for visualization
    - Context gathering for impact analysis
    
    Based on:
    - Ren2025HydraReviewer: Call graph analysis for cross-file dependencies
    - Meng2025RARe: Context expansion through dependency tracking
    
    Strategy: 
    1. Grep search for fast candidate discovery
    2. Tree-sitter validation to filter false positives
    3. Context extraction (code around call/import site)
    
    Depth: Only 1 level (direct callers/importers) for performance.
    """
    
    @abstractmethod
    async def find_callers(
        self,
        function_name: str,
        file_path: FilePath,
        repository: str,
        language: Language,
        ref: str = "HEAD",
    ) -> List[CallSite]:
        """Find all places where a function is called (1 level deep).
        
        Pure technical analysis - no semantic understanding.
        
        Algorithm:
        1. Grep search for function_name in repository (fast)
        2. Parse candidates with tree-sitter (validate actual calls)
        3. Extract context (5 lines around call site)
        4. Identify caller function name from AST
        
        Args:
            function_name: Name of the function to find calls for
            file_path: Path to file where function is defined
            repository: Repository identifier (owner/repo)
            language: Programming language of the function
            
        Returns:
            List of call sites where the function is invoked
            
        Raises:
            AnalysisError: If grep or tree-sitter parsing fails
            
        Example:
            Finding callers of validate_token() in auth.py:
            
            callers = await analyzer.find_callers(
                function_name="validate_token",
                file_path=FilePath("auth.py"),
                repository="owner/repo",
                language=Language("python")
            )
            
            # Returns: [
            #   CallSite(file="handlers/login.py", line=156, caller="handle_login", ...),
            #   CallSite(file="middleware/auth.py", line=78, caller="authenticate", ...)
            # ]
        """
        pass
    
    @abstractmethod
    async def find_importers(
        self,
        file_path: FilePath,
        repository: str,
        language: Language,
        ref: str = "HEAD",
    ) -> List[ImportSite]:
        """Find all files that import from a given module (1 level deep).
        
        Pure technical analysis - identifies import statements.
        
        Algorithm:
        1. Determine module name from file_path (e.g., "auth.py" → "auth")
        2. Grep search for import patterns ("import auth", "from auth import")
        3. Parse with tree-sitter to extract imported names
        4. Extract context (3 lines around import)
        
        Args:
            file_path: Path to the module file
            repository: Repository identifier
            language: Programming language
            
        Returns:
            List of import sites where the module is imported
            
        Raises:
            AnalysisError: If grep or tree-sitter parsing fails
            
        Example:
            Finding importers of auth.py:
            
            importers = await analyzer.find_importers(
                file_path=FilePath("auth.py"),
                repository="owner/repo",
                language=Language("python")
            )
            
            # Returns: [
            #   ImportSite(file="handlers/login.py", line=5, 
            #              imported_names=("validate_token", "refresh_token"), ...),
            #   ImportSite(file="tests/test_auth.py", line=3, ...)
            # ]
        """
        pass


class ImpactAnalyzer(ABC):
    """Port for semantic impact analysis of code changes using LLM.
    
    Analyzes whether changes to a function can break calling code.
    Requires LLMProvider for semantic understanding.
    
    Separate from CallGraphAnalyzer (SRP):
    - CallGraphAnalyzer: technical discovery (grep + tree-sitter)
    - ImpactAnalyzer: semantic analysis (LLM understanding)
    
    Based on:
    - Pornprasit2024FineTuningPromptingCR: Function isolation for context enhancement
    - Ren2025HydraReviewer: Breaking change detection through call graph
    
    Use cases:
    - Detect breaking changes (signature, semantics, contracts)
    - Generate fix suggestions for affected callers
    - Assess severity of changes (critical, high, medium, low)
    - Provide human-readable explanations
    """
    
    @abstractmethod
    async def analyze_impact(
        self,
        changed_function: FunctionNode,
        diff_hunk: DiffHunk,
        callers: List[CallSite],
        repository: str,
    ) -> ImpactAnalysisResult:
        """Analyze impact of a function change using LLM.
        
        LLM receives:
        - Changed function body (before/after from diff)
        - Diff showing what changed
        - List of callers with code context (from CallGraphAnalyzer)
        
        LLM analyzes:
        - Signature changes (parameters added/removed/renamed, return type changed)
        - Semantic changes (logic altered, edge cases handled differently)
        - Contract changes (preconditions, postconditions, invariants violated)
        - Side effects (new exceptions thrown, new dependencies introduced)
        
        For each caller, LLM determines:
        - Is it affected? (yes/no)
        - Why? (explanation of the issue)
        - What can break? (specific failure scenario)
        - How to fix? (code suggestion for caller)
        
        Args:
            changed_function: Function that was modified (from AST)
            diff_hunk: Diff showing the changes
            callers: List of places where function is called (from CallGraphAnalyzer)
            repository: Repository identifier
            
        Returns:
            Impact analysis result with:
            - List of breaking changes detected
            - Severity assessment (critical/high/medium/low)
            - Fix suggestions for each affected caller
            - Overall summary
            
        Raises:
            AnalysisError: If LLM call fails or response is invalid JSON
            
        Example:
            Analyzing impact of validate_token() signature change:
            
            # Get callers first (from CallGraphAnalyzer)
            callers = await call_graph_analyzer.find_callers(...)
            
            # Analyze impact with LLM
            impact = await impact_analyzer.analyze_impact(
                changed_function=FunctionNode(name="validate_token", ...),
                diff_hunk=DiffHunk(...),
                callers=callers,
                repository="owner/repo"
            )
            
            # Returns: ImpactAnalysisResult(
            #   breaking_changes=[
            #     BreakingChange(
            #       caller_file="handlers/login.py",
            #       caller_function="handle_login",
            #       issue="Signature changed - removed user_id parameter",
            #       suggested_fix="result = validate_token(request.token)",
            #       severity=Severity.ERROR
            #     )
            #   ],
            #   summary="Critical breaking changes detected. 2 callers affected."
            # )
        """
        pass


# Forward reference for type hints
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from acr_system.infrastructure.config.project_config import ProjectConfig
