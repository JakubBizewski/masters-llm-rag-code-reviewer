"""Use case: Index historical PR/MR changes into the vector store.

Goal:
- Build embeddings from historical merged PR diffs
- Store the discussion (comments + replies) so it can be used as RAG context
"""

import asyncio

from acr_system.application.dto.dto import PRHistoryIndexRequest, PRHistoryIndexResult
from acr_system.domain.interfaces.ports import EmbeddingStore, VCSRepository
from acr_system.shared.logging.logger import get_logger

logger = get_logger(__name__)


class IndexPRHistoryUseCase:
    """Indexes merged PR history for a repository."""

    def __init__(self, vcs_repository: VCSRepository, embedding_store: EmbeddingStore):
        self.vcs_repository = vcs_repository
        self.embedding_store = embedding_store

    async def execute(self, request: PRHistoryIndexRequest) -> PRHistoryIndexResult:
        indexed = 0
        skipped = 0

        try:
            pr_numbers = await self.vcs_repository.list_merged_pull_requests(
                repo=request.repository,
                limit=request.max_prs,
            )

            async def index_one(pr_number: int) -> None:
                nonlocal indexed, skipped
                try:
                    pr = await self.vcs_repository.get_pull_request(
                        repo=request.repository,
                        pr_number=pr_number,
                    )
                    hunks = await self.vcs_repository.get_diff_hunks(
                        repo=request.repository,
                        pr_number=pr_number,
                    )
                    for h in hunks:
                        pr.add_diff_hunk(h)

                    pr.discussion_comments = await self.vcs_repository.get_pull_request_discussion_comments(
                        repo=request.repository,
                        pr_number=pr_number,
                    )

                    await self.embedding_store.index_review_history(pr)
                    indexed += 1
                except Exception as e:
                    skipped += 1
                    logger.warning(
                        f"Skipping PR #{pr_number} during history indexing: {e}"
                    )

            # Keep concurrency bounded to avoid hitting API limits
            semaphore = asyncio.Semaphore(5)

            async def guarded(pr_number: int) -> None:
                async with semaphore:
                    await index_one(pr_number)

            await asyncio.gather(*(guarded(n) for n in pr_numbers))

            return PRHistoryIndexResult(
                repository=request.repository,
                indexed_count=indexed,
                skipped_count=skipped,
                success=True,
            )

        except Exception as e:
            logger.error(f"History indexing failed: {e}", exc_info=True)
            return PRHistoryIndexResult(
                repository=request.repository,
                indexed_count=indexed,
                skipped_count=skipped,
                success=False,
                error_message=str(e),
            )
