"""Domain services for orchestrating code review."""
from typing import Optional

from acr_system.domain.entities.entities import (
    CodeContext,
    DiffHunk,
    ParsedCIIssue,
    PullRequest,
    ReviewComment,
)
from acr_system.domain.interfaces.ports import (
    EmbeddingStore,
    LLMProvider,
    StaticAnalyzer,
    VCSRepository,
)
from acr_system.domain.value_objects.value_objects import RAGConfig


class ContextBuilder:
    """Service for building context for LLM from RAG and other sources."""
    
    def __init__(
        self,
        embedding_store: EmbeddingStore,
        vcs_repository: VCSRepository,
    ):
        self.embedding_store = embedding_store
        self.vcs_repository = vcs_repository
    
    async def build_context(
        self,
        diff_hunk: DiffHunk,
        pr: PullRequest,
        rag_config: Optional[RAGConfig] = None,
    ) -> list[CodeContext]:
        """Build context for a diff hunk.
        
        Context includes:
        - RAG retrieval from documentation
        - Surrounding code context
        - Previous review history
        """
        context: list[CodeContext] = []
        
        # RAG retrieval if enabled
        if rag_config and rag_config.enabled:
            query = self._build_rag_query(diff_hunk)
            rag_results = await self.embedding_store.search_similar(
                query=query,
                top_k=rag_config.top_k,
            )
            context.extend(rag_results)
        
        # Add surrounding code context
        surrounding_context = await self._get_surrounding_context(diff_hunk, pr)
        if surrounding_context:
            context.append(surrounding_context)
        
        return context
    
    def _build_rag_query(self, diff_hunk: DiffHunk) -> str:
        """Build search query for RAG from diff hunk."""
        # Extract key information from diff for better RAG retrieval
        lines = diff_hunk.content.split('\n')
        
        # Focus on added lines (they contain new code to review)
        added_lines = [line[1:] for line in lines if line.startswith('+') and not line.startswith('+++')]
        
        query = f"File: {diff_hunk.file_path.value}\n"
        query += f"Language: {diff_hunk.language.name}\n"
        query += "Changes:\n" + '\n'.join(added_lines[:10])  # Limit to first 10 lines
        
        return query
    
    async def _get_surrounding_context(
        self,
        diff_hunk: DiffHunk,
        pr: PullRequest,
    ) -> Optional[CodeContext]:
        """Get surrounding code context for a diff hunk."""
        try:
            # Get full file content from target branch
            file_content = await self.vcs_repository.get_file_content(
                repo=pr.repository,
                file_path=diff_hunk.file_path.value,
                ref=pr.target_branch,
            )
            
            # Extract relevant portion (few lines before and after)
            lines = file_content.split('\n')
            start = max(0, diff_hunk.new_start_line - 10)
            end = min(len(lines), diff_hunk.new_start_line + diff_hunk.new_line_count + 10)
            
            context_lines = lines[start:end]
            context_content = '\n'.join(context_lines)
            
            return CodeContext(
                content=context_content,
                source="surrounding_code",
                file_path=diff_hunk.file_path,
                relevance_score=1.0,  # High relevance for immediate context
            )
        except Exception:
            # If we can't get context, return None (non-critical)
            return None


class ReviewOrchestrator:
    """Main service for orchestrating code review process."""
    
    def __init__(
        self,
        llm_provider: LLMProvider,
        context_builder: ContextBuilder,
        static_analyzer: Optional[StaticAnalyzer] = None,
    ):
        self.llm_provider = llm_provider
        self.context_builder = context_builder
        self.static_analyzer = static_analyzer
    
    async def review_pull_request(
        self,
        pr: PullRequest,
        rules_text: str,
        rag_config: Optional[RAGConfig] = None,
    ) -> list[ReviewComment]:
        """Review a pull request and generate comments.
        
        Args:
            pr: Pull request to review
            rules_text: Rules to apply for review
            rag_config: RAG configuration
            
        Returns:
            List of review comments
        """
        all_comments: list[ReviewComment] = []
        
        # Fetch CI results if analyzer available
        ci_issues: list[ParsedCIIssue] = []
        if self.static_analyzer:
            ci_results = await self.static_analyzer.fetch_ci_results(
                repo=pr.repository,
                pr_number=pr.pr_number,
            )
            
            # Parse CI results with LLM
            for ci_result in ci_results:
                parsed = await self.llm_provider.parse_ci_output(
                    ci_result=ci_result,
                    changed_files=pr.changed_files,
                )
                ci_issues.extend(parsed)
        
        # Review each diff hunk
        for hunk in pr.diff_hunks:
            # Build context for this hunk
            context = await self.context_builder.build_context(
                diff_hunk=hunk,
                pr=pr,
                rag_config=rag_config,
            )
            
            # Filter CI issues relevant to this hunk
            relevant_ci_issues = [
                issue for issue in ci_issues
                if issue.file_path == hunk.file_path.value
                and (issue.line_number is None or hunk.is_line_in_hunk(issue.line_number))
            ]
            
            # Generate review comments with LLM
            comments = await self.llm_provider.generate_review_comments(
                diff_hunk=hunk,
                rules_text=rules_text,
                context=context,
                ci_issues=relevant_ci_issues,
            )
            
            all_comments.extend(comments)
        
        return all_comments
    
    async def review_diff_hunk(
        self,
        hunk: DiffHunk,
        pr: PullRequest,
        rules_text: str,
        ci_issues: list[ParsedCIIssue],
        rag_config: Optional[RAGConfig] = None,
    ) -> list[ReviewComment]:
        """Review a single diff hunk.
        
        This method allows more granular control over the review process.
        """
        # Build context
        context = await self.context_builder.build_context(
            diff_hunk=hunk,
            pr=pr,
            rag_config=rag_config,
        )
        
        # Generate comments
        comments = await self.llm_provider.generate_review_comments(
            diff_hunk=hunk,
            rules_text=rules_text,
            context=context,
            ci_issues=ci_issues,
        )
        
        return comments
