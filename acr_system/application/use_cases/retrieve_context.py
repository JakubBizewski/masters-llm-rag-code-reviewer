"""Use case: Retrieve Context for RAG."""
from acr_system.application.dto.dto import ContextRetrievalRequest
from acr_system.domain.entities.entities import CodeContext
from acr_system.domain.interfaces.ports import EmbeddingStore
from acr_system.shared.logging.logger import get_logger

logger = get_logger(__name__)


class RetrieveContextUseCase:
    """Use case for retrieving context from RAG."""
    
    def __init__(self, embedding_store: EmbeddingStore):
        self.embedding_store = embedding_store
    
    async def execute(self, request: ContextRetrievalRequest) -> list[CodeContext]:
        """Execute context retrieval.
        
        Args:
            request: Context retrieval request
            
        Returns:
            List of relevant code contexts
        """
        try:
            logger.info(f"Retrieving context for query: {request.query[:100]}...")
            
            contexts = await self.embedding_store.search_similar(
                query=request.query,
                top_k=request.top_k,
                filters=request.filters,
            )
            
            logger.info(f"Retrieved {len(contexts)} relevant contexts")
            return contexts
            
        except Exception as e:
            logger.error(f"Error retrieving context: {e}", exc_info=True)
            return []
