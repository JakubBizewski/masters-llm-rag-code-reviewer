"""Use case: Publish Review Comments."""
from acr_system.application.dto.dto import ReviewPublishRequest
from acr_system.domain.interfaces.ports import VCSRepository
from acr_system.shared.logging.logger import get_logger

logger = get_logger(__name__)


class PublishReviewUseCase:
    """Use case for publishing review comments to VCS."""
    
    def __init__(self, vcs_repository: VCSRepository):
        self.vcs_repository = vcs_repository
    
    async def execute(self, request: ReviewPublishRequest) -> bool:
        """Execute publishing review comments.
        
        Args:
            request: Publish request
            
        Returns:
            Success status
        """
        try:
            logger.info(
                f"Publishing {len(request.comments)} comments to "
                f"PR #{request.pr_number} in {request.repository}"
            )
            
            await self.vcs_repository.post_review_comments(
                repo=request.repository,
                pr_number=request.pr_number,
                comments=request.comments,
            )
            
            logger.info("Successfully published review comments")
            return True
            
        except Exception as e:
            logger.error(f"Error publishing review: {e}", exc_info=True)
            return False
