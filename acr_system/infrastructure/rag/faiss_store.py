"""FAISS vector store for RAG."""
from typing import Optional

try:
    import faiss
    import numpy as np
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    faiss = None  # type: ignore
    np = None  # type: ignore

from acr_system.domain.entities.entities import (
    ArchitecturalDocument,
    CodeContext,
    PullRequest,
)
from acr_system.domain.interfaces.ports import EmbeddingStore
from acr_system.shared.exceptions.infrastructure_exceptions import EmbeddingStoreError
from acr_system.shared.logging.logger import get_logger

logger = get_logger(__name__)


class FAISSStore(EmbeddingStore):
    """FAISS-based vector store for RAG retrieval."""
    
    def __init__(self, embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        if not FAISS_AVAILABLE:
            raise EmbeddingStoreError(
                "FAISS not installed. Install with: pip install faiss-cpu sentence-transformers"
            )
        
        self.embedding_model_name = embedding_model_name
        self.index: Optional[faiss.Index] = None  # type: ignore
        self.documents: list[dict] = []
        self.dimension = 384  # Default for MiniLM
        
        # Lazy load embedding model
        self._embedding_model = None
    
    @property
    def embedding_model(self):  # type: ignore
        """Lazy load embedding model."""
        if self._embedding_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._embedding_model = SentenceTransformer(self.embedding_model_name)
                self.dimension = self._embedding_model.get_sentence_embedding_dimension()
            except ImportError:
                raise EmbeddingStoreError(
                    "sentence-transformers not installed. "
                    "Install with: pip install sentence-transformers"
                )
        return self._embedding_model
    
    def _initialize_index(self) -> None:
        """Initialize FAISS index."""
        if self.index is None:
            # Use L2 distance (can be changed to inner product)
            self.index = faiss.IndexFlatL2(self.dimension)  # type: ignore
    
    def _embed_text(self, text: str) -> np.ndarray:  # type: ignore
        """Generate embedding for text."""
        return self.embedding_model.encode([text])[0]
    
    async def index_documents(
        self,
        documents: list[ArchitecturalDocument],
    ) -> None:
        """Index documents for RAG retrieval."""
        try:
            self._initialize_index()
            
            for doc in documents:
                # Generate embedding
                embedding = self._embed_text(doc.content)
                
                # Add to FAISS index
                self.index.add(np.array([embedding], dtype=np.float32))  # type: ignore
                
                # Store document metadata
                self.documents.append({
                    "filename": doc.filename,
                    "content": doc.content,
                    "source": "documentation",
                })
            
            logger.info(f"Indexed {len(documents)} documents")
            
        except Exception as e:
            raise EmbeddingStoreError(f"Error indexing documents: {e}") from e
    
    async def search_similar(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[dict[str, str]] = None,
    ) -> list[CodeContext]:
        """Search for similar code contexts."""
        try:
            if self.index is None or self.index.ntotal == 0:
                logger.warning("No documents indexed yet")
                return []
            
            # Generate query embedding
            query_embedding = self._embed_text(query)
            
            # Search FAISS index
            distances, indices = self.index.search(
                np.array([query_embedding], dtype=np.float32),  # type: ignore
                min(top_k, self.index.ntotal)
            )
            
            # Build CodeContext results
            contexts = []
            for i, (distance, idx) in enumerate(zip(distances[0], indices[0])):
                if idx < len(self.documents):
                    doc = self.documents[idx]
                    
                    # Convert L2 distance to similarity score (0-1)
                    # Lower distance = higher similarity
                    similarity = 1.0 / (1.0 + float(distance))
                    
                    context = CodeContext(
                        content=doc["content"],
                        source=doc["source"],
                        relevance_score=similarity,
                    )
                    contexts.append(context)
            
            return contexts
            
        except Exception as e:
            logger.error(f"Error searching similar contexts: {e}", exc_info=True)
            return []
    
    async def index_review_history(
        self,
        pr: PullRequest,
    ) -> None:
        """Index PR review for future RAG retrieval."""
        try:
            self._initialize_index()
            
            # Create document from PR review
            content = f"""Pull Request: {pr.title}
Repository: {pr.repository}
Files changed: {', '.join(pr.changed_files)}

Review Comments:
"""
            for comment in pr.review_comments:
                content += f"- [{comment.severity}] {comment.file_path}: {comment.message}\n"
            
            # Generate embedding
            embedding = self._embed_text(content)
            
            # Add to index
            self.index.add(np.array([embedding], dtype=np.float32))  # type: ignore
            
            # Store metadata
            self.documents.append({
                "filename": f"PR-{pr.pr_number}",
                "content": content,
                "source": "previous_review",
            })
            
            logger.info(f"Indexed review history for PR #{pr.pr_number}")
            
        except Exception as e:
            logger.warning(f"Error indexing review history: {e}")
