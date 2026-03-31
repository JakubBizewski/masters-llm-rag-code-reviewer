"""Use case: Process Pull Request for code review."""
import asyncio
from typing import Optional

from acr_system.application.dto.dto import PRReviewRequest, ReviewResult
from acr_system.ast.parser import ASTParser
from acr_system.domain.interfaces.ports import (
    ConfigRepository,
    EmbeddingStore,
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
        embedding_store: EmbeddingStore,
        config_repository: ConfigRepository,
        context_builder: ContextBuilder,
        review_orchestrator: ReviewOrchestrator,
    ):
        self.vcs_repository = vcs_repository
        self.embedding_store = embedding_store
        self.config_repository = config_repository
        self.context_builder = context_builder
        self.review_orchestrator = review_orchestrator
    
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
            
            # Helper function to review a single file with all its hunks in parallel
            async def review_single_file(file_path: str):
                """Review a single file - helper for parallel processing."""
                logger.info(f"Reviewing file: {file_path}")
                
                # Get rules, RAG config, and LLM config for this file
                rules_text, rag_config, llm_config = await self.config_repository.get_rules_for_file(
                    config=config,
                    file_path=file_path,
                )
                
                # Get hunks for this file
                file_hunks = pr.get_hunks_for_file(file_path)
                
                # Helper function to review a single hunk
                async def review_single_hunk(hunk):
                    """Review a single hunk - nested helper for parallel processing."""
                    return await self.review_orchestrator.review_diff_hunk(
                        hunk=hunk,
                        pr=pr,
                        rules_text=rules_text,
                        llm_config=llm_config,
                        ci_issues=[],  # CI issues handled by orchestrator
                        rag_config=rag_config,
                    )
                
                # Process all hunks in this file in parallel
                hunk_tasks = [review_single_hunk(hunk) for hunk in file_hunks]
                hunk_comments_lists = await asyncio.gather(*hunk_tasks, return_exceptions=True)
                
                # Flatten results and handle exceptions
                file_comments = []
                for result in hunk_comments_lists:
                    if isinstance(result, Exception):
                        logger.error(f"Error reviewing hunk in {file_path}: {result}")
                        continue
                    file_comments.extend(result)
                
                return file_comments
            
            # Process all files in parallel
            file_tasks = [review_single_file(file_path) for file_path in pr.changed_files]
            file_comments_lists = await asyncio.gather(*file_tasks, return_exceptions=True)
            
            # Flatten results and handle exceptions
            for result in file_comments_lists:
                if isinstance(result, Exception):
                    logger.error(f"Error reviewing file: {result}")
                    continue
                all_comments.extend(result)
            
            logger.info(f"Generated {len(all_comments)} review comments")
            
            # 4. Index this review for future RAG
            try:
                pr.discussion_comments = (
                    await self.vcs_repository.get_pull_request_discussion_comments(
                        repo=request.repository,
                        pr_number=request.pr_number,
                    )
                )
            except Exception as e:
                logger.debug(
                    f"Failed to fetch discussion comments for PR #{request.pr_number}: {e}"
                )

            try:
                await self.embedding_store.index_review_history(pr)
            except Exception as e:
                logger.warning(
                    f"Failed to index review history for PR #{request.pr_number}: {e}"
                )
            
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
