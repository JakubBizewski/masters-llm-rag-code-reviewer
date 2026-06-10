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
    PullRequestDiscussionComment,
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
            "retrieved_chunks": 0,
        }
        # Log of every search_similar call made during the review phase.
        # Each entry: {query, filters, returned: [{source, relevance_score, content_excerpt}]}
        self.retrieval_log: list[dict] = []

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
            "retrieved_chunks": 0,
        }
        self.retrieval_log = []

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

            source_filter = None
            exclude_pr_number = None
            simple_filters: dict[str, str] = {}
            if filters:
                source_filter = filters.get("source")
                exclude_pr_number = filters.get("exclude_pr_number") or filters.get(
                    "exclude_pr_number_if_thread_exists"
                )
                simple_filters = {
                    k: v
                    for k, v in filters.items()
                    if k not in {
                        "source",
                        "exclude_pr_number",
                        "exclude_pr_number_if_thread_exists",
                    }
                }

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

                    if source_filter:
                        if source_filter == "pr_history":
                            if not str(doc.get("source", "")).startswith("pr_history"):
                                continue
                        elif doc.get("source") != source_filter:
                            continue

                    if simple_filters:
                        matches = all(doc.get(k) == v for k, v in simple_filters.items())
                        if not matches:
                            continue

                    if exclude_pr_number and doc.get("pr_number") == exclude_pr_number:
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

            self.stats["retrieved_chunks"] += len(contexts)
            self.retrieval_log.append({
                "query": query[:600],
                "filters": filters,
                "returned": [
                    {
                        "source": c.source,
                        "relevance_score": round(c.relevance_score, 4),
                        "content_excerpt": c.content[:400],
                    }
                    for c in contexts
                ],
            })
            return contexts
            
        except Exception as e:
            logger.error(f"Error searching similar contexts: {e}", exc_info=True)
            return []
    
    async def index_review_history(
        self,
        pr: PullRequest,
    ) -> None:
        """Index PR review history for future RAG retrieval.

        Approach:
        - Index each discussion thread (root comment + replies) as a separate document.
        - Include minimal diff context (best-effort) for the comment's file/line.
        - If the PR has no discussion comments, index a single diff-only document.
        """
        try:
            self._initialize_index()
            existing_keys = _existing_unique_keys(self.documents)

            by_parent, roots = _build_discussion_threads(pr)

            common_header = (
                f"Pull Request #{pr.pr_number}: {pr.title}\n"
                f"Repository: {pr.repository}\n"
                f"Author: {pr.author}\n"
                f"Source branch: {pr.source_branch}\n"
                f"Target branch: {pr.target_branch}\n"
                f"Files changed: {', '.join(sorted(pr.changed_files))}\n"
            )

            if not roots:
                unique_key = _make_unique_key(
                    repo=pr.repository,
                    pr_number=pr.pr_number,
                    kind="diff",
                    identifier="no-discussion",
                )
                if unique_key in existing_keys:
                    logger.info(
                        f"Skipping diff-only history for PR #{pr.pr_number}; already indexed"
                    )
                    return

                diff_text = _format_full_diff(pr)
                content = (
                    f"{common_header}\n"
                    f"=== DIFF ===\n{diff_text}\n"
                )

                content = _truncate_for_embedding(content, max_chars=25_000)
                embedding = self._embed_text(content)
                self.index.add(np.array([embedding], dtype=np.float32))  # type: ignore
                self.documents.append({
                    "filename": f"PR-{pr.pr_number}-diff",
                    "content": content,
                    "source": "pr_history_diff",
                    "repo": pr.repository,
                    "pr_number": str(pr.pr_number),
                    "unique_key": unique_key,
                })

                self._persist()
                logger.info(
                    f"Indexed diff-only history for PR #{pr.pr_number} (no discussion comments)"
                )
                return

            indexed_threads = 0
            skipped_threads = 0
            for root in roots:
                unique_key = _make_unique_key(
                    repo=pr.repository,
                    pr_number=pr.pr_number,
                    kind="comment_thread",
                    identifier=str(root.comment_id),
                )
                if unique_key in existing_keys:
                    skipped_threads += 1
                    continue

                diff_context = _format_diff_context_for_comment(pr, root)
                thread_text = _format_thread(root, by_parent)

                location = ""
                if root.file_path and root.line_number:
                    location = f" ({root.file_path.value}:{root.line_number})"
                elif root.file_path:
                    location = f" ({root.file_path.value})"

                content = (
                    f"{common_header}"
                    f"Thread root comment #{root.comment_id}{location}\n\n"
                    f"=== DIFF CONTEXT (best-effort) ===\n{diff_context}\n\n"
                    f"=== DISCUSSION THREAD (comment + replies) ===\n{thread_text}\n"
                )

                content = _truncate_for_embedding(content, max_chars=20_000)
                embedding = self._embed_text(content)
                self.index.add(np.array([embedding], dtype=np.float32))  # type: ignore
                self.documents.append({
                    "filename": f"PR-{pr.pr_number}-comment-{root.comment_id}",
                    "content": content,
                    "source": "pr_history_comment_thread",
                    "repo": pr.repository,
                    "pr_number": str(pr.pr_number),
                    "comment_id": str(root.comment_id),
                    "file_path": root.file_path.value if root.file_path else None,
                    "line_number": str(root.line_number) if root.line_number else None,
                    "url": getattr(root, "url", None),
                    "unique_key": unique_key,
                })
                existing_keys.add(unique_key)
                indexed_threads += 1
                logger.info(
                    f"Indexed discussion thread for comment #{root.comment_id} in PR #{pr.pr_number}"
                )

            if indexed_threads > 0:
                self._persist()
            logger.info(
                f"Indexed {indexed_threads} discussion threads for PR #{pr.pr_number} "
                f"(skipped duplicates: {skipped_threads})"
            )
            
        except Exception as e:
            logger.warning(f"Error indexing review history: {e}")


def _format_discussion(pr: PullRequest) -> str:
    """Format discussion comments (including replies) into a readable thread."""
    if not getattr(pr, "discussion_comments", None):
        return "(no comments)"

    comments: list[PullRequestDiscussionComment] = list(pr.discussion_comments)
    by_parent: dict[Optional[int], list[PullRequestDiscussionComment]] = {}
    by_id: dict[int, PullRequestDiscussionComment] = {}
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
    top_level: list[PullRequestDiscussionComment] = []
    for c in by_parent.get(None, []):
        top_level.append(c)
    for parent_id, lst in by_parent.items():
        if parent_id is not None and parent_id not in by_id:
            top_level.extend(lst)

    # Deduplicate while keeping order
    seen: set[int] = set()
    ordered_top: list[PullRequestDiscussionComment] = []
    for c in top_level:
        if c.comment_id in seen:
            continue
        seen.add(c.comment_id)
        ordered_top.append(c)

    return "\n".join(fmt_one(c, indent=0) for c in ordered_top)


def _make_unique_key(repo: str, pr_number: int, kind: str, identifier: str) -> str:
    return f"{repo}::pr:{pr_number}::{kind}:{identifier}"


def _existing_unique_keys(documents: list[dict]) -> set[str]:
    keys: set[str] = set()
    for doc in documents:
        key = doc.get("unique_key")
        if isinstance(key, str) and key:
            keys.add(key)
            continue

        # Backward compatibility for older persisted metadata without unique_key
        source = doc.get("source")
        repo = doc.get("repo")
        pr_number = doc.get("pr_number")
        if not (isinstance(repo, str) and isinstance(pr_number, str)):
            continue

        try:
            pr_number_int = int(pr_number)
        except ValueError:
            continue

        if source == "pr_history_diff":
            keys.add(_make_unique_key(repo, pr_number_int, "diff", "no-discussion"))
        elif source == "pr_history_comment_thread":
            comment_id = doc.get("comment_id")
            if isinstance(comment_id, str) and comment_id:
                keys.add(_make_unique_key(repo, pr_number_int, "comment_thread", comment_id))

    return keys


def _truncate_for_embedding(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[TRUNCATED]"


def _format_full_diff(pr: PullRequest) -> str:
    diff_text_parts: list[str] = []
    for hunk in pr.diff_hunks:
        diff_text_parts.append(f"### {hunk.file_path.value}\n{hunk.content}")
    return "\n\n".join(diff_text_parts) or "(no diff hunks)"


def _build_discussion_threads(
    pr: PullRequest,
) -> tuple[
    dict[Optional[int], list[PullRequestDiscussionComment]],
    list[PullRequestDiscussionComment],
]:
    """Return (by_parent, ordered_roots) for discussion comments."""
    if not getattr(pr, "discussion_comments", None):
        return {}, []

    comments: list[PullRequestDiscussionComment] = list(pr.discussion_comments)
    by_parent: dict[Optional[int], list[PullRequestDiscussionComment]] = {}
    by_id: dict[int, PullRequestDiscussionComment] = {}
    for c in comments:
        by_id[c.comment_id] = c
        by_parent.setdefault(c.in_reply_to_id, []).append(c)

    for lst in by_parent.values():
        lst.sort(key=lambda x: x.created_at)

    top_level: list[PullRequestDiscussionComment] = []
    for c in by_parent.get(None, []):
        top_level.append(c)
    for parent_id, lst in by_parent.items():
        if parent_id is not None and parent_id not in by_id:
            top_level.extend(lst)

    seen: set[int] = set()
    ordered_roots: list[PullRequestDiscussionComment] = []
    for c in top_level:
        if c.comment_id in seen:
            continue
        seen.add(c.comment_id)
        ordered_roots.append(c)

    return by_parent, ordered_roots


def _format_thread(
    root_comment: PullRequestDiscussionComment,
    by_parent: dict[Optional[int], list[PullRequestDiscussionComment]],
) -> str:
    """Format a single thread (root + replies) as text."""

    def fmt_one(c: PullRequestDiscussionComment, indent: int = 0) -> str:
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

    return fmt_one(root_comment, indent=0)


def _format_diff_context_for_comment(
    pr: PullRequest,
    comment: PullRequestDiscussionComment,
) -> str:
    """Best-effort diff context for a comment's file/line."""
    if not comment.file_path:
        return "(no file context)"

    hunks = pr.get_hunks_for_file(comment.file_path.value)
    if not hunks:
        return f"### {comment.file_path.value}\n(no diff hunks for file)"

    selected = []
    if comment.line_number is not None:
        selected = [h for h in hunks if h.is_line_in_hunk(int(comment.line_number))]

    if not selected:
        selected = hunks[:2]

    parts: list[str] = [f"### {comment.file_path.value}"]
    for h in selected:
        header = (
            f"@@ -{h.old_start_line},{h.old_line_count} "
            f"+{h.new_start_line},{h.new_line_count} @@"
        )
        parts.append(f"{header}\n{h.content}")
    return "\n\n".join(parts)
