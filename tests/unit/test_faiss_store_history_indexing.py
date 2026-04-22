from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import acr_system.infrastructure.rag.faiss_store as faiss_store
from acr_system.domain.entities.entities import (
    DiffHunk,
    PullRequest,
    PullRequestDiscussionComment,
)
from acr_system.domain.value_objects.value_objects import FilePath
from acr_system.infrastructure.rag.faiss_store import FAISSStore


class _FakeIndexFlatL2:
    def __init__(self, d: int):
        self.d = int(d)
        self._vectors: list[list[float]] = []

    @property
    def ntotal(self) -> int:
        return len(self._vectors)

    def add(self, vectors) -> None:  # vectors is list[list[float]]
        for v in vectors:
            self._vectors.append(list(v))

    def search(self, query_vectors, k):  # noqa: ARG002
        k = max(0, min(int(k), self.ntotal))
        distances = [[float(i) for i in range(k)]]
        indices = [[i for i in range(k)]]
        return distances, indices


class _FakeNP:
    float32 = "float32"

    def array(self, x, dtype=None):  # noqa: ARG002
        return x


class _FakeEmbeddingModel:
    def __init__(self, dim: int):
        self._dim = int(dim)

    def get_sentence_embedding_dimension(self) -> int:
        return self._dim

    def encode(self, texts):
        return [[0.0 for _ in range(self._dim)] for _ in texts]


@pytest.mark.asyncio
async def test_index_review_history_indexes_one_document_per_thread(monkeypatch, tmp_path):
    # Make the module think FAISS/NumPy are available
    monkeypatch.setattr(faiss_store, "FAISS_AVAILABLE", True)
    monkeypatch.setattr(
        faiss_store,
        "faiss",
        SimpleNamespace(IndexFlatL2=_FakeIndexFlatL2, write_index=lambda *a, **k: None),
    )
    monkeypatch.setattr(faiss_store, "np", _FakeNP())

    # Avoid filesystem persistence for a pure unit test
    monkeypatch.setattr(FAISSStore, "_load_if_exists", lambda self: None)
    monkeypatch.setattr(FAISSStore, "_persist", lambda self: None)

    store = FAISSStore(storage_path=str(tmp_path))
    store._embedding_model = _FakeEmbeddingModel(dim=3)
    store.dimension = 3

    pr = PullRequest(
        pr_number=1,
        repository="owner/repo",
        title="Test PR",
        description="",
        author="alice",
        source_branch="feature",
        target_branch="main",
    )

    pr.add_diff_hunk(
        DiffHunk(
            file_path=FilePath("a.py"),
            old_start_line=1,
            old_line_count=1,
            new_start_line=9,
            new_line_count=5,
            content="@@ -1,1 +9,5 @@\n+print('x')\n",
        )
    )

    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)

    root_1 = PullRequestDiscussionComment(
        comment_id=1,
        author="bob",
        body="Root comment",
        created_at=t0,
        file_path=FilePath("a.py"),
        line_number=10,
        in_reply_to_id=None,
    )
    reply_1 = PullRequestDiscussionComment(
        comment_id=2,
        author="carol",
        body="Reply to root",
        created_at=t0,
        file_path=FilePath("a.py"),
        line_number=10,
        in_reply_to_id=1,
    )
    root_2 = PullRequestDiscussionComment(
        comment_id=3,
        author="dave",
        body="Another root",
        created_at=t0,
        in_reply_to_id=None,
    )

    pr.discussion_comments = [root_1, reply_1, root_2]

    await store.index_review_history(pr)

    assert store.index is not None
    assert store.index.ntotal == 2
    assert len(store.documents) == 2

    # Should track one embedding per thread
    assert store.stats["embedding_texts"] == 2
    assert store.stats["embedding_tokens"] > 0

    by_comment_id = {doc.get("comment_id"): doc for doc in store.documents}

    assert by_comment_id["1"]["source"] == "pr_history_comment_thread"
    assert "Root comment" in by_comment_id["1"]["content"]
    assert "Reply to root" in by_comment_id["1"]["content"]

    assert by_comment_id["3"]["source"] == "pr_history_comment_thread"
    assert "Another root" in by_comment_id["3"]["content"]


@pytest.mark.asyncio
async def test_index_review_history_is_idempotent_for_same_pr(monkeypatch, tmp_path):
    monkeypatch.setattr(faiss_store, "FAISS_AVAILABLE", True)
    monkeypatch.setattr(
        faiss_store,
        "faiss",
        SimpleNamespace(IndexFlatL2=_FakeIndexFlatL2, write_index=lambda *a, **k: None),
    )
    monkeypatch.setattr(faiss_store, "np", _FakeNP())
    monkeypatch.setattr(FAISSStore, "_load_if_exists", lambda self: None)
    monkeypatch.setattr(FAISSStore, "_persist", lambda self: None)

    store = FAISSStore(storage_path=str(tmp_path))
    store._embedding_model = _FakeEmbeddingModel(dim=3)
    store.dimension = 3

    pr = PullRequest(
        pr_number=7,
        repository="owner/repo",
        title="Idempotency PR",
        description="",
        author="alice",
        source_branch="feature",
        target_branch="main",
    )
    pr.add_diff_hunk(
        DiffHunk(
            file_path=FilePath("a.py"),
            old_start_line=1,
            old_line_count=1,
            new_start_line=20,
            new_line_count=4,
            content="@@ -1,1 +20,4 @@\n+print('x')\n",
        )
    )
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    pr.discussion_comments = [
        PullRequestDiscussionComment(
            comment_id=11,
            author="bob",
            body="Root",
            created_at=t0,
            file_path=FilePath("a.py"),
            line_number=21,
            in_reply_to_id=None,
        )
    ]

    await store.index_review_history(pr)
    first_vectors = store.index.ntotal if store.index is not None else 0
    first_docs = len(store.documents)
    first_embeds = store.stats["embedding_texts"]

    await store.index_review_history(pr)

    assert store.index is not None
    assert store.index.ntotal == first_vectors
    assert len(store.documents) == first_docs
    assert store.stats["embedding_texts"] == first_embeds


@pytest.mark.asyncio
async def test_search_similar_excludes_current_pr(monkeypatch, tmp_path):
    monkeypatch.setattr(faiss_store, "FAISS_AVAILABLE", True)
    monkeypatch.setattr(
        faiss_store,
        "faiss",
        SimpleNamespace(IndexFlatL2=_FakeIndexFlatL2, write_index=lambda *a, **k: None),
    )
    monkeypatch.setattr(faiss_store, "np", _FakeNP())
    monkeypatch.setattr(FAISSStore, "_load_if_exists", lambda self: None)

    store = FAISSStore(storage_path=str(tmp_path))
    store._embedding_model = _FakeEmbeddingModel(dim=3)
    store.dimension = 3
    store._initialize_index()

    assert store.index is not None
    store.index.add([[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]])
    store.documents = [
        {
            "content": "current pr thread",
            "source": "pr_history_comment_thread",
            "repo": "owner/repo",
            "pr_number": "7",
            "comment_id": "11",
        },
        {
            "content": "current pr diff",
            "source": "pr_history_diff",
            "repo": "owner/repo",
            "pr_number": "7",
        },
        {
            "content": "older pr thread",
            "source": "pr_history_comment_thread",
            "repo": "owner/repo",
            "pr_number": "6",
            "comment_id": "9",
        },
    ]

    results = await store.search_similar(
        query="cache changes",
        top_k=3,
        filters={
            "source": "pr_history",
            "repo": "owner/repo",
            "exclude_pr_number": "7",
        },
    )

    assert [r.content for r in results] == ["older pr thread"]


@pytest.mark.asyncio
async def test_search_similar_excludes_current_pr_even_when_only_diff_exists(monkeypatch, tmp_path):
    monkeypatch.setattr(faiss_store, "FAISS_AVAILABLE", True)
    monkeypatch.setattr(
        faiss_store,
        "faiss",
        SimpleNamespace(IndexFlatL2=_FakeIndexFlatL2, write_index=lambda *a, **k: None),
    )
    monkeypatch.setattr(faiss_store, "np", _FakeNP())
    monkeypatch.setattr(FAISSStore, "_load_if_exists", lambda self: None)

    store = FAISSStore(storage_path=str(tmp_path))
    store._embedding_model = _FakeEmbeddingModel(dim=3)
    store.dimension = 3
    store._initialize_index()

    assert store.index is not None
    store.index.add([[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]])
    store.documents = [
        {
            "content": "current pr diff",
            "source": "pr_history_diff",
            "repo": "owner/repo",
            "pr_number": "7",
        },
        {
            "content": "older pr thread",
            "source": "pr_history_comment_thread",
            "repo": "owner/repo",
            "pr_number": "6",
            "comment_id": "9",
        },
    ]

    results = await store.search_similar(
        query="cache changes",
        top_k=2,
        filters={
            "source": "pr_history",
            "repo": "owner/repo",
            "exclude_pr_number": "7",
        },
    )

    assert [r.content for r in results] == ["older pr thread"]
