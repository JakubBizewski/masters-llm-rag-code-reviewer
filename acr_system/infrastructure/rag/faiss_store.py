"""FAISS vector store for RAG."""
import json
import os
from pathlib import Path
from typing import Optional
from acr_system.shared.utils.token_counter import approx_token_count

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
    
    def __init__(
        self,
        embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        storage_path: Optional[str] = None,
    ):
        if not FAISS_AVAILABLE:
            raise EmbeddingStoreError(
                "FAISS not installed. Install with: pip install faiss-cpu sentence-transformers"
            )
        
        self.embedding_model_name = embedding_model_name
        self.index: Optional[faiss.Index] = None  # type: ignore
        self.documents: list[dict] = []
        self.dimension = 384  # Default for MiniLM

        # Persistence
        self.storage_dir = Path(
            storage_path
            or os.getenv("RAG_FAISS_INDEX_PATH", "./faiss_index")
        )
        self.index_file = self.storage_dir / "index.faiss"
        self.metadata_file = self.storage_dir / "documents.json"
        
        # Lazy load embedding model
        self._embedding_model = None

        # Lightweight accounting for experimental evaluation
        self.stats: dict[str, int] = {
            "embedding_tokens": 0,
            "embedding_texts": 0,
        }

        # Best-effort load persisted index
        self._load_if_exists()
    
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

    def _load_if_exists(self) -> None:
        """Load persisted index/documents if present."""
        try:
            if not self.index_file.exists() or not self.metadata_file.exists():
                return

            self.index = faiss.read_index(str(self.index_file))  # type: ignore
            self.dimension = int(getattr(self.index, "d", self.dimension))

            with self.metadata_file.open("r", encoding="utf-8") as f:
                payload = json.load(f)

            # Backward compatible: allow plain list
            if isinstance(payload, dict):
                self.documents = payload.get("documents", [])
                stored_model = payload.get("embedding_model_name")
                if stored_model and stored_model != self.embedding_model_name:
                    logger.warning(
                        "FAISSStore loaded documents created with a different embedding model. "
                        "Consider rebuilding the index for best results."
                    )
            elif isinstance(payload, list):
                self.documents = payload
            else:
                self.documents = []

            if self.index is not None and self.index.ntotal != len(self.documents):
                logger.warning(
                    "FAISS index/documents size mismatch; starting with empty store"
                )
                self.index = None
                self.documents = []

            if self.index is not None:
                logger.info(
                    f"Loaded FAISS index with {self.index.ntotal} vectors from {self.storage_dir}"
                )
        except Exception as e:
            logger.warning(f"Failed to load FAISS index: {e}")
            self.index = None
            self.documents = []

    def _persist(self) -> None:
        """Persist FAISS index/documents to disk (best-effort)."""
        try:
            if self.index is None:
                return

            self.storage_dir.mkdir(parents=True, exist_ok=True)
            faiss.write_index(self.index, str(self.index_file))  # type: ignore

            payload = {
                "embedding_model_name": self.embedding_model_name,
                "dimension": self.dimension,
                "documents": self.documents,
            }
            with self.metadata_file.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed to persist FAISS index: {e}")
    
    def reset_stats(self) -> None:
        self.stats = {
            "embedding_tokens": 0,
            "embedding_texts": 0,
        }

    def _embed_text(self, text: str) -> np.ndarray:  # type: ignore
        """Generate embedding for text (also counts approximate tokens)."""
        self.stats["embedding_tokens"] += approx_token_count(text)
        self.stats["embedding_texts"] += 1
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

            self._persist()
            
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
            
            requested_k = min(max(int(top_k), 1), int(self.index.ntotal))
            # Over-fetch so we can apply metadata filters after ANN search
            search_k = min(max(requested_k * 5, requested_k), int(self.index.ntotal))

            # Search FAISS index
            distances, indices = self.index.search(
                np.array([query_embedding], dtype=np.float32),  # type: ignore
                search_k,
            )
            
            # Build CodeContext results
            contexts = []
            for distance, idx in zip(distances[0], indices[0]):
                if idx < len(self.documents):
                    doc = self.documents[idx]

                    if filters:
                        matches = all(doc.get(k) == v for k, v in filters.items())
                        if not matches:
                            continue
                    
                    # Convert L2 distance to similarity score (0-1)
                    # Lower distance = higher similarity
                    similarity = 1.0 / (1.0 + float(distance))
                    
                    context = CodeContext(
                        content=doc["content"],
                        source=doc["source"],
                        relevance_score=similarity,
                    )
                    contexts.append(context)

                    if len(contexts) >= requested_k:
                        break
            
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
            
            diff_text_parts: list[str] = []
            for hunk in pr.diff_hunks:
                diff_text_parts.append(f"### {hunk.file_path.value}\n{hunk.content}")
            diff_text = "\n\n".join(diff_text_parts)

            discussion_text = _format_discussion(pr)

            # Create document from PR history (diff + discussion)
            content = (
                f"Pull Request #{pr.pr_number}: {pr.title}\n"
                f"Repository: {pr.repository}\n"
                f"Author: {pr.author}\n"
                f"Source branch: {pr.source_branch}\n"
                f"Target branch: {pr.target_branch}\n"
                f"Files changed: {', '.join(sorted(pr.changed_files))}\n\n"
                f"=== DIFF ===\n{diff_text}\n\n"
                f"=== DISCUSSION (comments + replies) ===\n{discussion_text}\n"
            )

            # Cap text size for embedding cost/performance
            max_chars = 25_000
            if len(content) > max_chars:
                content = content[:max_chars] + "\n\n[TRUNCATED]"
            
            # Generate embedding
            embedding = self._embed_text(content)
            
            # Add to index
            self.index.add(np.array([embedding], dtype=np.float32))  # type: ignore
            
            # Store metadata
            self.documents.append({
                "filename": f"PR-{pr.pr_number}",
                "content": content,
                "source": "pr_history",
                "repo": pr.repository,
                "pr_number": str(pr.pr_number),
            })

            self._persist()
            
            logger.info(f"Indexed review history for PR #{pr.pr_number}")
            
        except Exception as e:
            logger.warning(f"Error indexing review history: {e}")


def _format_discussion(pr: PullRequest) -> str:
    """Format discussion comments (including replies) into a readable thread."""
    if not getattr(pr, "discussion_comments", None):
        return "(no comments)"

    comments = list(pr.discussion_comments)
    by_parent: dict[Optional[int], list] = {}
    by_id: dict[int, object] = {}
    for c in comments:
        by_id[c.comment_id] = c
        by_parent.setdefault(c.in_reply_to_id, []).append(c)

    # Keep stable chronological order
    for lst in by_parent.values():
        lst.sort(key=lambda x: x.created_at)

    def fmt_one(c, indent: int = 0) -> str:
        prefix = "  " * indent
        location = ""
        if c.file_path and c.line_number:
            location = f" ({c.file_path.value}:{c.line_number})"
        elif c.file_path:
            location = f" ({c.file_path.value})"

        header = f"{prefix}- {c.author}{location}:"
        body_lines = (c.body or "").splitlines() or [""]
        body = "\n".join(f"{prefix}  {line}" for line in body_lines)

        parts = [header, body]
        replies = by_parent.get(c.comment_id, [])
        for r in replies:
            parts.append(fmt_one(r, indent=indent + 1))
        return "\n".join(parts)

    # Top-level = no parent OR parent missing
    top_level: list = []
    for c in by_parent.get(None, []):
        top_level.append(c)
    for parent_id, lst in by_parent.items():
        if parent_id is not None and parent_id not in by_id:
            top_level.extend(lst)

    # Deduplicate while keeping order
    seen: set[int] = set()
    ordered_top: list = []
    for c in top_level:
        if c.comment_id in seen:
            continue
        seen.add(c.comment_id)
        ordered_top.append(c)

    return "\n".join(fmt_one(c, indent=0) for c in ordered_top)
