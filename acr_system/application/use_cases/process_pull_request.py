"""Use case: Process Pull Request for code review."""
from typing import Optional

from acr_system.application.dto.dto import PRReviewRequest, ReviewResult
from acr_system.domain.interfaces.ports import (
    ConfigRepository,
    EmbeddingStore,
    LLMProvider,
    StaticAnalyzer,
    VCSRepository,
)
from acr_system.domain.services.services import ContextBuilder, ReviewOrchestrator
from acr_system.shared.logging.logger import get_logger

logger = get_logger(__name__)


class ProcessPullRequestUseCase:
    """Use case for processing a pull request review."""
    
    def __init__(
        self,
        vcs_repository: VCSRepository,
        llm_provider: LLMProvider,
        embedding_store: EmbeddingStore,
        config_repository: ConfigRepository,
        static_analyzer: Optional[StaticAnalyzer] = None,
    ):
        self.vcs_repository = vcs_repository
        self.llm_provider = llm_provider
        self.embedding_store = embedding_store
        self.config_repository = config_repository
        self.static_analyzer = static_analyzer
        
        # Initialize domain services
        self.context_builder = ContextBuilder(
            embedding_store=embedding_store,
            vcs_repository=vcs_repository,
        )
        
        self.review_orchestrator = ReviewOrchestrator(
            llm_provider=llm_provider,
            context_builder=self.context_builder,
            static_analyzer=static_analyzer,
        )
    
    async def execute(self, request: PRReviewRequest) -> ReviewResult:
        """Execute the pull request review use case.
        
        Args:
            request: PR review request
            
        Returns:
            Review result with comments
        """
        try:
            logger.info(
                f"Starting review for PR #{request.pr_number} in {request.repository}"
            )
            
            # 1. Fetch PR details and diff
            pr = await self.vcs_repository.get_pull_request(
                repo=request.repository,
                pr_number=request.pr_number,
            )
            
            diff_hunks = await self.vcs_repository.get_diff_hunks(
                repo=request.repository,
                pr_number=request.pr_number,
            )
            
            for hunk in diff_hunks:
                pr.add_diff_hunk(hunk)
            
            logger.info(f"Fetched {len(diff_hunks)} diff hunks for {len(pr.changed_files)} files")
            
            # 2. Load project configuration
            config = await self.config_repository.load_config(
                repo=request.repository,
                ref=pr.target_branch,
            )
            
            # 3. Review each file with appropriate rules
            all_comments = []
            
            for file_path in pr.changed_files:
                logger.info(f"Reviewing file: {file_path}")
                
                # Get rules for this file
                rules_text, rag_config = await self.config_repository.get_rules_for_file(
                    config=config,
                    file_path=file_path,
                )
                
                # Get hunks for this file
                file_hunks = pr.get_hunks_for_file(file_path)
                
                # Review with orchestrator
                for hunk in file_hunks:
                    comments = await self.review_orchestrator.review_diff_hunk(
                        hunk=hunk,
                        pr=pr,
                        rules_text=rules_text,
                        ci_issues=[],  # CI issues handled by orchestrator
                        rag_config=rag_config,
                    )
                    all_comments.extend(comments)
            
            logger.info(f"Generated {len(all_comments)} review comments")
            
            # 4. Index this review for future RAG
            await self.embedding_store.index_review_history(pr)
            
            return ReviewResult(
                repository=request.repository,
                pr_number=request.pr_number,
                comments=all_comments,
                success=True,
            )
            
        except Exception as e:
            logger.error(f"Error processing PR review: {e}", exc_info=True)
            return ReviewResult(
                repository=request.repository,
                pr_number=request.pr_number,
                comments=[],
                success=False,
                error_message=str(e),
            )
