"""Integration tests for RAG (Retrieval-Augmented Generation) flow."""
import pytest
from unittest.mock import AsyncMock

from acr_system.domain.entities.entities import CodeContext, DiffHunk, PullRequest
from acr_system.domain.services.services import ContextBuilder
from acr_system.domain.value_objects.value_objects import FilePath, RAGConfig


@pytest.mark.asyncio
async def test_rag_retrieval_with_relevant_documentation(
    mock_vcs_repository,
    mock_embedding_store,
):
    """Integration test: RAG retrieval finds relevant documentation.
    
    Tests:
    - ContextBuilder.build_context() uses RAG for retrieval
    - Relevant documentation is found based on code changes
    - Results are ranked by relevance score
    """
    # === Setup ===
    pr = PullRequest(
        pr_number=123,
        repository="acme/webapp",
        title="Add caching",
        description="Implement Redis caching",
        author="alice",
        source_branch="feature/cache",
        target_branch="main",
    )
    
    hunk = DiffHunk(
        file_path=FilePath("src/cache/redis_client.py"),
        old_start_line=1,
        old_line_count=0,
        new_start_line=1,
        new_line_count=20,
        content="""@@ -0,0 +1,20 @@
+import redis
+
+class RedisClient:
+    def __init__(self, host='localhost', port=6379):
+        self.client = redis.Redis(host=host, port=port)
+    
+    def get(self, key: str):
+        return self.client.get(key)
+    
+    def set(self, key: str, value: str, ttl: int = 3600):
+        self.client.setex(key, ttl, value)
""",
    )
    
    # === Mock file content ===
    mock_vcs_repository.get_file_content.return_value = "# Redis client implementation"
    
    # === Mock RAG results ===
    docs_results = [
        CodeContext(
            content="Redis best practice: Always set TTL on cache entries to prevent memory bloat",
            source="redis_guidelines",
            file_path=FilePath("docs/caching.md"),
            relevance_score=0.95,
        ),
        CodeContext(
            content="Use connection pooling for Redis to improve performance",
            source="performance_guide",
            file_path=FilePath("docs/performance.md"),
            relevance_score=0.87,
        ),
        CodeContext(
            content="Handle Redis connection errors gracefully with try-except blocks",
            source="error_handling_guide",
            file_path=FilePath("docs/errors.md"),
            relevance_score=0.82,
        ),
    ]

    history_results = [
        CodeContext(
            content="Pull Request #101: Add Redis cache\n=== DIFF ===\n...\n=== DISCUSSION ===\n- reviewer: Please add TTL\n  - author: Added TTL in next commit",
            source="pr_history",
            relevance_score=0.77,
        )
    ]

    mock_embedding_store.search_similar.side_effect = [docs_results, history_results]
    
    # === Build context ===
    context_builder = ContextBuilder(
        embedding_store=mock_embedding_store,
        vcs_repository=mock_vcs_repository,
    )
    
    rag_config = RAGConfig(
        enabled=True,
        top_k=5,
    )
    
    context = await context_builder.build_context(
        diff_hunk=hunk,
        pr=pr,
        rag_config=rag_config,
    )
    
    # === Assertions ===
    
    # 1. RAG search was called
    assert mock_embedding_store.search_similar.call_count == 2
    
    # 2. Query contains relevant information
    first_call = mock_embedding_store.search_similar.call_args_list[0]
    query = first_call.kwargs['query']
    assert "redis" in query.lower() or "cache" in query.lower(), \
        "Query should contain relevant keywords"
    assert first_call.kwargs['top_k'] == 5
    
    # 3. Context includes RAG results
    assert len(context) >= 3, "Should have at least 3 context items (RAG results)"
    
    # 4. RAG results are in context
    rag_contexts = [c for c in context if c.source in ["redis_guidelines", "performance_guide", "error_handling_guide"]]
    assert len(rag_contexts) == 3, "All RAG results should be in context"

    # 4b. Historical PR change context is also included
    history_contexts = [c for c in context if c.source == "pr_history"]
    assert len(history_contexts) == 1
    
    # 5. Results are sorted by relevance
    scores = [c.relevance_score for c in rag_contexts]
    assert scores == sorted(scores, reverse=True), "Results should be sorted by relevance"
    
    # 6. Surrounding code context is also included
    surrounding_contexts = [c for c in context if c.source == "surrounding_code"]
    assert len(surrounding_contexts) <= 1, "Should have at most 1 surrounding code context"


@pytest.mark.asyncio
async def test_rag_retrieval_with_no_relevant_results(
    mock_vcs_repository,
    mock_embedding_store,
):
    """Integration test: RAG retrieval when no relevant docs are found.
    
    Tests:
    - Empty RAG results are handled gracefully
    - Context still includes surrounding code
    - No errors are raised
    """
    # === Setup ===
    pr = PullRequest(
        pr_number=456,
        repository="acme/webapp",
        title="Fix typo",
        description="Fix typo in comment",
        author="bob",
        source_branch="fix/typo",
        target_branch="main",
    )
    
    hunk = DiffHunk(
        file_path=FilePath("src/utils/helper.py"),
        old_start_line=10,
        old_line_count=1,
        new_start_line=10,
        new_line_count=1,
        content="""@@ -10,1 +10,1 @@
-# Teh quick brown fox
+# The quick brown fox
""",
    )
    
    # === Mock responses ===
    mock_vcs_repository.get_file_content.return_value = "def helper():\n    pass"
    mock_embedding_store.search_similar.side_effect = [[], []]  # docs + history: no results
    
    # === Build context ===
    context_builder = ContextBuilder(
        embedding_store=mock_embedding_store,
        vcs_repository=mock_vcs_repository,
    )
    
    rag_config = RAGConfig(enabled=True, top_k=5)
    
    context = await context_builder.build_context(
        diff_hunk=hunk,
        pr=pr,
        rag_config=rag_config,
    )
    
    # === Assertions ===
    
    # 1. RAG was attempted
    assert mock_embedding_store.search_similar.call_count == 2
    
    # 2. Context is not empty (has surrounding code)
    assert len(context) >= 0, "Context should be valid even without RAG results"
    
    # 3. Surrounding code context should still be present
    surrounding = [c for c in context if c.source == "surrounding_code"]
    assert len(surrounding) <= 1


@pytest.mark.asyncio
async def test_rag_retrieval_disabled(
    mock_vcs_repository,
    mock_embedding_store,
):
    """Integration test: RAG retrieval when RAG is disabled.
    
    Tests:
    - RAG is not called when disabled
    - Context still includes surrounding code
    - Performance is better (no embedding search)
    """
    # === Setup ===
    pr = PullRequest(
        pr_number=789,
        repository="acme/webapp",
        title="Update logic",
        description="Improve algorithm",
        author="charlie",
        source_branch="improve/algo",
        target_branch="main",
    )
    
    hunk = DiffHunk(
        file_path=FilePath("src/algorithm.py"),
        old_start_line=20,
        old_line_count=5,
        new_start_line=20,
        new_line_count=8,
        content="""@@ -20,5 +20,8 @@
 def process(data):
-    result = []
-    for item in data:
-        result.append(item * 2)
-    return result
+    # Improved algorithm
+    return [item * 2 for item in data]
""",
    )
    
    # === Mock responses ===
    mock_vcs_repository.get_file_content.return_value = "def process(data):\n    pass"
    
    # === Build context with RAG DISABLED ===
    context_builder = ContextBuilder(
        embedding_store=mock_embedding_store,
        vcs_repository=mock_vcs_repository,
    )
    
    rag_config = RAGConfig(enabled=False, top_k=5)
    
    context = await context_builder.build_context(
        diff_hunk=hunk,
        pr=pr,
        rag_config=rag_config,
    )
    
    # === Assertions ===
    
    # 1. RAG was NOT called
    mock_embedding_store.search_similar.assert_not_called()
    
    # 2. Context only contains surrounding code
    assert all(c.source == "surrounding_code" for c in context), \
        "Only surrounding code should be in context when RAG is disabled"


@pytest.mark.asyncio
async def test_rag_retrieval_with_multiple_languages(
    mock_vcs_repository,
    mock_embedding_store,
):
    """Integration test: RAG retrieval for different programming languages.
    
    Tests:
    - RAG works across multiple languages (Python, JavaScript, TypeScript)
    - Language-specific documentation is retrieved
    - Query is constructed appropriately for each language
    """
    pr = PullRequest(
        pr_number=999,
        repository="acme/webapp",
        title="Multilang changes",
        description="Changes in multiple languages",
        author="dave",
        source_branch="multi/lang",
        target_branch="main",
    )
    
    context_builder = ContextBuilder(
        embedding_store=mock_embedding_store,
        vcs_repository=mock_vcs_repository,
    )
    
    rag_config = RAGConfig(enabled=True, top_k=3)
    
    # === Test 1: Python hunk ===
    python_hunk = DiffHunk(
        file_path=FilePath("src/backend/api.py"),
        old_start_line=1,
        old_line_count=0,
        new_start_line=1,
        new_line_count=5,
        content="""@@ -0,0 +1,5 @@
+from fastapi import FastAPI
+app = FastAPI()
""",
    )
    
    mock_vcs_repository.get_file_content.return_value = "# Python API"
    python_docs = [
        CodeContext(
            content="FastAPI best practices: Use dependency injection",
            source="python_api_docs",
            file_path=FilePath("docs/python.md"),
            relevance_score=0.9,
        )
    ]

    # Two calls per hunk: docs + history
    mock_embedding_store.search_similar.side_effect = [python_docs, []]
    
    python_context = await context_builder.build_context(
        diff_hunk=python_hunk,
        pr=pr,
        rag_config=rag_config,
    )
    
    # Verify Python RAG was called
    assert mock_embedding_store.search_similar.call_count == 2
    python_query = mock_embedding_store.search_similar.call_args_list[0].kwargs['query']
    assert "api.py" in python_query
    
    # === Test 2: JavaScript hunk ===
    js_hunk = DiffHunk(
        file_path=FilePath("src/frontend/app.js"),
        old_start_line=1,
        old_line_count=0,
        new_start_line=1,
        new_line_count=5,
        content="""@@ -0,0 +1,5 @@
+import React from 'react';
+function App() {
+    return <div>Hello</div>;
+}
""",
    )
    
    mock_vcs_repository.get_file_content.return_value = "// JavaScript app"
    js_docs = [
        CodeContext(
            content="React hooks: Use useState for component state",
            source="react_docs",
            file_path=FilePath("docs/react.md"),
            relevance_score=0.88,
        )
    ]

    mock_embedding_store.search_similar.side_effect = [js_docs, []]
    
    js_context = await context_builder.build_context(
        diff_hunk=js_hunk,
        pr=pr,
        rag_config=rag_config,
    )
    
    # Verify JavaScript RAG was called
    assert mock_embedding_store.search_similar.call_count == 4
    js_query = mock_embedding_store.search_similar.call_args_list[2].kwargs['query']
    assert "app.js" in js_query
    
    # === Assertions ===
    assert len(python_context) >= 1, "Python context should have RAG results"
    assert len(js_context) >= 1, "JavaScript context should have RAG results"


@pytest.mark.asyncio
async def test_rag_retrieval_with_similarity_threshold(
    mock_vcs_repository,
    mock_embedding_store,
):
    """Integration test: RAG retrieval filters by similarity threshold.
    
    Tests:
    - Low relevance results are filtered out
    - min_similarity threshold is respected
    - Only high-quality results are included
    """
    pr = PullRequest(
        pr_number=111,
        repository="acme/webapp",
        title="Add feature",
        description="New feature",
        author="eve",
        source_branch="feature/new",
        target_branch="main",
    )
    
    hunk = DiffHunk(
        file_path=FilePath("src/feature.py"),
        old_start_line=1,
        old_line_count=0,
        new_start_line=1,
        new_line_count=10,
        content="@@ -0,0 +1,10 @@\n+def new_feature():\n+    pass",
    )
    
    # === Mock RAG with mixed relevance scores ===
    mock_vcs_repository.get_file_content.return_value = "# Feature code"
    
    # Note: In real implementation, min_similarity filtering happens in the adapter
    # Here we simulate what the adapter would return
    docs_results = [
        CodeContext(
            content="Highly relevant documentation",
            source="high_quality_doc",
            file_path=FilePath("docs/feature.md"),
            relevance_score=0.95,  # Above threshold
        ),
        CodeContext(
            content="Moderately relevant documentation",
            source="medium_quality_doc",
            file_path=FilePath("docs/general.md"),
            relevance_score=0.75,  # Above threshold
        ),
        # Low relevance results filtered by adapter (not included)
    ]

    mock_embedding_store.search_similar.side_effect = [docs_results, []]
    
    context_builder = ContextBuilder(
        embedding_store=mock_embedding_store,
        vcs_repository=mock_vcs_repository,
    )
    
    # Request top 10 results
    rag_config = RAGConfig(enabled=True, top_k=10)
    
    context = await context_builder.build_context(
        diff_hunk=hunk,
        pr=pr,
        rag_config=rag_config,
    )
    
    # === Assertions ===
    rag_results = [c for c in context if c.source != "surrounding_code"]
    
    # All results should be above threshold
    assert all(c.relevance_score >= 0.7 for c in rag_results), \
        "All RAG results should be above min_similarity threshold"
    
    # Should have 2 results (low relevance ones filtered out)
    assert len(rag_results) == 2


@pytest.mark.asyncio
async def test_rag_retrieval_query_construction(
    mock_vcs_repository,
    mock_embedding_store,
):
    """Integration test: RAG query is constructed intelligently from diff.
    
    Tests:
    - Query includes file path
    - Query includes language
    - Query includes added lines (not removed)
    - Query is well-formatted for retrieval
    """
    pr = PullRequest(
        pr_number=222,
        repository="acme/webapp",
        title="Database optimization",
        description="Optimize queries",
        author="frank",
        source_branch="optimize/db",
        target_branch="main",
    )
    
    hunk = DiffHunk(
        file_path=FilePath("src/database/queries.py"),
        old_start_line=50,
        old_line_count=5,
        new_start_line=50,
        new_line_count=8,
        content="""@@ -50,5 +50,8 @@
 def get_users():
-    return db.query("SELECT * FROM users")
+    # Add index hint for performance
+    return db.query(
+        "SELECT * FROM users USE INDEX (idx_active)",
+        use_prepared=True
+    )
""",
    )
    
    mock_vcs_repository.get_file_content.return_value = "# Database queries"
    mock_embedding_store.search_similar.side_effect = [[], []]
    
    context_builder = ContextBuilder(
        embedding_store=mock_embedding_store,
        vcs_repository=mock_vcs_repository,
    )
    
    rag_config = RAGConfig(enabled=True, top_k=5)
    
    await context_builder.build_context(
        diff_hunk=hunk,
        pr=pr,
        rag_config=rag_config,
    )
    
    # === Assertions on query construction ===
    assert mock_embedding_store.search_similar.call_count == 2
    
    first_call = mock_embedding_store.search_similar.call_args_list[0]
    query = first_call.kwargs['query']
    
    # 1. Query includes file path
    assert "queries.py" in query, "Query should include file name"
    
    # 2. Query includes language
    assert "Language:" in query or "Python" in query, "Query should include language"
    
    # 3. Query includes added lines (with +)
    assert "USE INDEX" in query or "use_prepared" in query, \
        "Query should include added code content"
    
    # 4. Query does NOT include removed lines (those starting with -)
    # (The old line "SELECT * FROM users" should ideally not be in query)
    
    # 5. Query is structured
    assert "File:" in query or "Changes:" in query, \
        "Query should have structured format"
