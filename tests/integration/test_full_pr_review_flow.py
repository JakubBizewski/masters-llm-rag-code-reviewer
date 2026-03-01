"""Integration tests for full PR review flow."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from acr_system.application.dto.dto import PRReviewRequest
from acr_system.application.use_cases.process_pull_request import ProcessPullRequestUseCase
from acr_system.domain.entities.entities import (
    CodeContext,
    DiffHunk,
    ParsedCIIssue,
    PullRequest,
    ReviewComment,
)
from acr_system.domain.value_objects.value_objects import (
    FilePath,
    RAGConfig,
    RuleSet,
    Severity,
)
from acr_system.infrastructure.config.project_config import ProjectConfig


@pytest.mark.asyncio
async def test_full_pr_review_flow_end_to_end(
    mock_vcs_repository,
    mock_llm_provider,
    mock_embedding_store,
    mock_config_repository,
):
    """Integration test: Complete end-to-end PR review flow.
    
    This test simulates the entire flow:
    1. Webhook receives PR
    2. Fetch PR and diff from VCS
    3. Load config from repository
    4. Build context with RAG
    5. Generate review comments with LLM
    6. Parse CI results
    7. Index review history
    """
    # === Setup: Create realistic PR with multiple files ===
    pr = PullRequest(
        pr_number=456,
        repository="acme/webapp",
        title="Add user authentication",
        description="Implements JWT-based authentication for user login",
        author="alice",
        source_branch="feature/auth",
        target_branch="main",
    )
    
    # Multiple diff hunks (different files)
    hunk1 = DiffHunk(
        file_path=FilePath("src/auth/login.py"),
        old_start_line=1,
        old_line_count=0,
        new_start_line=1,
        new_line_count=15,
        content="""@@ -0,0 +1,15 @@
+import jwt
+from datetime import datetime, timedelta
+
+def generate_token(user_id: str) -> str:
+    payload = {
+        'user_id': user_id,
+        'exp': datetime.utcnow() + timedelta(hours=24)
+    }
+    return jwt.encode(payload, 'SECRET_KEY', algorithm='HS256')
+
+def verify_token(token: str) -> dict:
+    try:
+        return jwt.decode(token, 'SECRET_KEY', algorithms=['HS256'])
+    except jwt.ExpiredSignatureError:
+        return None
""",
    )
    
    hunk2 = DiffHunk(
        file_path=FilePath("src/api/routes.py"),
        old_start_line=50,
        old_line_count=3,
        new_start_line=50,
        new_line_count=10,
        content="""@@ -50,3 +50,10 @@
 def get_user(user_id: str):
     return db.get_user(user_id)
 
+@app.post("/login")
+def login(username: str, password: str):
+    user = authenticate(username, password)
+    if user:
+        token = generate_token(user.id)
+        return {"token": token}
+    return {"error": "Invalid credentials"}, 401
""",
    )
    
    pr.add_diff_hunk(hunk1)
    pr.add_diff_hunk(hunk2)
    
    # === Mock VCS responses ===
    mock_vcs_repository.get_pull_request.return_value = pr
    mock_vcs_repository.get_diff_hunks.return_value = [hunk1, hunk2]
    
    # Mock file content for context building
    mock_vcs_repository.get_file_content.side_effect = lambda repo, file_path, ref: {
        "src/auth/login.py": "# New file\n",
        "src/api/routes.py": "\n".join([
            "from flask import Flask, request",
            "app = Flask(__name__)",
            "",
            "def get_user(user_id: str):",
            "    return db.get_user(user_id)",
        ]),
    }.get(file_path, "")
    
    # === Mock config with RAG enabled ===
    config = ProjectConfig(
        global_rules=[
            RuleSet(
                name="security",
                enabled=True,
                rules_text="Check for security vulnerabilities, hardcoded secrets, SQL injection",
            ),
            RuleSet(
                name="code_quality",
                enabled=True,
                rules_text="Check for code smells, error handling, type hints",
            )
        ],
        rag_enabled=True,
        rag_top_k=5,
        llm_model="gpt-4",
        llm_temperature=0.3,
    )
    
    mock_config_repository.load_config.return_value = config
    
    # Per-file rules
    def get_rules_for_file(config, file_path):
        if "auth" in file_path:
            return (
                "Security rules: No hardcoded secrets, proper JWT validation",
                RAGConfig(enabled=True, top_k=5),
            )
        elif "routes" in file_path:
            return (
                "API rules: Proper error handling, input validation",
                RAGConfig(enabled=True, top_k=3),
            )
        return (config.global_rules[0].rules_text, None)
    
    mock_config_repository.get_rules_for_file.side_effect = get_rules_for_file
    
    # === Mock RAG (embedding store) responses ===
    def mock_rag_search(query: str, top_k: int):
        """Return relevant documentation based on query."""
        if "jwt" in query.lower() or "auth" in query.lower():
            return [
                CodeContext(
                    content="Best practice: Store JWT secret in environment variables, not in code",
                    source="security_docs",
                    file_path=FilePath("docs/security.md"),
                    relevance_score=0.92,
                ),
                CodeContext(
                    content="JWT tokens should have expiration time. Use short-lived tokens (1-24 hours)",
                    source="auth_guidelines",
                    file_path=FilePath("docs/auth.md"),
                    relevance_score=0.88,
                ),
            ]
        elif "api" in query.lower() or "routes" in query.lower():
            return [
                CodeContext(
                    content="API endpoints must validate input and return proper HTTP status codes",
                    source="api_standards",
                    file_path=FilePath("docs/api.md"),
                    relevance_score=0.85,
                ),
            ]
        return []
    
    mock_embedding_store.search_similar.side_effect = mock_rag_search
    mock_embedding_store.index_review_history.return_value = None
    
    # === Mock LLM responses ===
    
    # Mock CI parsing
    mock_llm_provider.parse_ci_output.return_value = [
        ParsedCIIssue(
            tool_name="Bandit",
            file_path="src/auth/login.py",
            line_number=9,
            severity="high",
            issue_code="B105",
            message="Hardcoded password string detected: 'SECRET_KEY'",
        )
    ]
    
    # Mock review comment generation (called per hunk)
    review_comments_hunk1 = [
        ReviewComment(
            file_path=FilePath("src/auth/login.py"),
            line_number=9,
            severity=Severity(level=Severity.ERROR),
            message="🔴 **Security Issue**: Hardcoded secret key detected.\n\n"
                    "The JWT secret key 'SECRET_KEY' is hardcoded in the code. "
                    "This is a critical security vulnerability.\n\n"
                    "**Recommendation**: Store the secret in an environment variable:\n"
                    "```python\nimport os\nSECRET_KEY = os.getenv('JWT_SECRET_KEY')\n```",
            suggestion="Use environment variable for JWT secret",
            rule_name="security.no_hardcoded_secrets",
        ),
        ReviewComment(
            file_path=FilePath("src/auth/login.py"),
            line_number=15,
            severity=Severity(level=Severity.WARNING),
            message="⚠️ Consider adding error logging in the exception handler",
            rule_name="code_quality.error_handling",
        ),
    ]
    
    review_comments_hunk2 = [
        ReviewComment(
            file_path=FilePath("src/api/routes.py"),
            line_number=54,
            severity=Severity(level=Severity.WARNING),
            message="⚠️ Missing input validation for username and password parameters",
            rule_name="code_quality.input_validation",
        ),
        ReviewComment(
            file_path=FilePath("src/api/routes.py"),
            line_number=58,
            severity=Severity(level=Severity.INFO),
            message="💡 Consider using proper HTTP status code constant (HTTP_401_UNAUTHORIZED)",
            rule_name="code_quality.http_codes",
        ),
    ]
    
    # Side effect to return different comments per hunk
    call_count = 0
    def generate_comments_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return review_comments_hunk1
        else:
            return review_comments_hunk2
    
    mock_llm_provider.generate_review_comments.side_effect = generate_comments_side_effect
    
    # === Mock CI adapter ===
    mock_ci_adapter = AsyncMock()
    mock_ci_adapter.fetch_ci_results.return_value = [
        MagicMock(
            tool_name="Bandit",
            status="failure",
            raw_output="src/auth/login.py:9:1: B105 Hardcoded password string",
            files_mentioned={"src/auth/login.py"},
            conclusion="failure",
        )
    ]
    
    # === Execute use case ===
    use_case = ProcessPullRequestUseCase(
        vcs_repository=mock_vcs_repository,
        llm_provider=mock_llm_provider,
        embedding_store=mock_embedding_store,
        config_repository=mock_config_repository,
        static_analyzer=mock_ci_adapter,
    )
    
    request = PRReviewRequest(repository="acme/webapp", pr_number=456)
    result = await use_case.execute(request)
    
    # === Assertions ===
    
    # 1. Overall success
    assert result.success, f"Review should succeed, but got error: {result.error_message}"
    
    # 2. Comments were generated
    assert result.comment_count > 0, "Should generate review comments"
    assert result.comment_count == 4, f"Expected 4 comments, got {result.comment_count}"
    
    # 3. Severity breakdown
    assert result.error_count == 1, "Should have 1 error (hardcoded secret)"
    assert result.warning_count == 2, "Should have 2 warnings"
    assert result.info_count == 1, "Should have 1 info comment"
    
    # 4. VCS interactions
    mock_vcs_repository.get_pull_request.assert_called_once_with(
        repo="acme/webapp",
        pr_number=456,
    )
    mock_vcs_repository.get_diff_hunks.assert_called_once()
    
    # 5. Config loading
    mock_config_repository.load_config.assert_called_once()
    
    # 6. RAG was used (search_similar called for both hunks)
    assert mock_embedding_store.search_similar.call_count >= 2, \
        "RAG should be queried for each hunk"
    
    # 7. LLM was called
    assert mock_llm_provider.generate_review_comments.call_count == 2, \
        "LLM should generate comments for 2 hunks"
    
    # 8. CI integration
    mock_ci_adapter.fetch_ci_results.assert_called_once()
    mock_llm_provider.parse_ci_output.assert_called_once()
    
    # 9. Review was indexed for future RAG
    mock_embedding_store.index_review_history.assert_called_once()
    
    # 10. Comments have correct structure
    assert all(isinstance(c, ReviewComment) for c in result.comments)
    assert all(hasattr(c, 'file_path') for c in result.comments)
    assert all(hasattr(c, 'severity') for c in result.comments)
    
    # 11. Critical security issue is flagged
    security_comments = [c for c in result.comments if c.severity.level == Severity.ERROR]
    assert len(security_comments) > 0, "Should flag critical security issue"
    assert any("SECRET_KEY" in c.message for c in security_comments)


@pytest.mark.asyncio
async def test_full_pr_review_flow_with_large_pr_chunking(
    mock_vcs_repository,
    mock_llm_provider,
    mock_embedding_store,
    mock_config_repository,
):
    """Integration test: Large PR that requires chunking.
    
    Tests:
    - PR with >500 lines triggers chunking logic
    - Each chunk is processed independently
    - Comments are aggregated from all chunks
    """
    # === Setup: Large PR with many changes ===
    pr = PullRequest(
        pr_number=789,
        repository="acme/webapp",
        title="Refactor database layer",
        description="Major refactoring of database code",
        author="bob",
        source_branch="refactor/db",
        target_branch="main",
    )
    
    # Create multiple hunks simulating large PR (>500 lines total)
    hunks = []
    for i in range(10):  # 10 files × 60 lines = 600 lines total
        hunk = DiffHunk(
            file_path=FilePath(f"src/db/model_{i}.py"),
            old_start_line=1,
            old_line_count=50,
            new_start_line=1,
            new_line_count=60,
            content=f"@@ -1,50 +1,60 @@\n" + "\n".join([f"+ line {j}" for j in range(60)]),
        )
        hunks.append(hunk)
        pr.add_diff_hunk(hunk)
    
    # === Mock responses ===
    mock_vcs_repository.get_pull_request.return_value = pr
    mock_vcs_repository.get_diff_hunks.return_value = hunks
    mock_vcs_repository.get_file_content.return_value = "# Python file"
    
    config = ProjectConfig(
        global_rules=[
            RuleSet(name="quality", enabled=True, rules_text="Check code quality")
        ],
        max_chunk_size=500,  # Trigger chunking
        rag_enabled=False,
    )
    
    mock_config_repository.load_config.return_value = config
    mock_config_repository.get_rules_for_file.return_value = ("Check quality", None)
    
    # Mock LLM to return 1 comment per hunk
    mock_llm_provider.generate_review_comments.return_value = [
        ReviewComment(
            file_path=FilePath("src/db/model_0.py"),
            line_number=10,
            severity=Severity(level=Severity.INFO),
            message="Looks good",
        )
    ]
    
    mock_embedding_store.search_similar.return_value = []
    mock_embedding_store.index_review_history.return_value = None
    
    # === Execute ===
    use_case = ProcessPullRequestUseCase(
        vcs_repository=mock_vcs_repository,
        llm_provider=mock_llm_provider,
        embedding_store=mock_embedding_store,
        config_repository=mock_config_repository,
        static_analyzer=None,
    )
    
    request = PRReviewRequest(repository="acme/webapp", pr_number=789)
    result = await use_case.execute(request)
    
    # === Assertions ===
    assert result.success
    
    # With 10 hunks, should have processed all of them
    assert mock_llm_provider.generate_review_comments.call_count == 10, \
        "Should process all 10 hunks"
    
    # Should aggregate comments from all hunks
    assert result.comment_count == 10, "Should have 10 comments (1 per hunk)"


@pytest.mark.asyncio
async def test_full_pr_review_flow_with_error_handling(
    mock_vcs_repository,
    mock_llm_provider,
    mock_embedding_store,
    mock_config_repository,
):
    """Integration test: Error handling in PR review flow.
    
    Tests:
    - Graceful handling of VCS errors
    - Graceful handling of LLM errors
    - Error messages are properly propagated
    """
    # === Test 1: VCS error (PR not found) ===
    mock_vcs_repository.get_pull_request.side_effect = Exception("PR not found")
    
    use_case = ProcessPullRequestUseCase(
        vcs_repository=mock_vcs_repository,
        llm_provider=mock_llm_provider,
        embedding_store=mock_embedding_store,
        config_repository=mock_config_repository,
        static_analyzer=None,
    )
    
    request = PRReviewRequest(repository="acme/webapp", pr_number=999)
    result = await use_case.execute(request)
    
    # Should fail gracefully
    assert not result.success
    assert result.error_message is not None
    assert "PR not found" in result.error_message
    assert result.comment_count == 0


@pytest.mark.asyncio
async def test_full_pr_review_flow_with_no_changes(
    mock_vcs_repository,
    mock_llm_provider,
    mock_embedding_store,
    mock_config_repository,
):
    """Integration test: PR with no actual code changes (only whitespace/comments).
    
    Tests:
    - Empty PR is handled gracefully
    - No LLM calls are made for empty PR
    - Success is still reported
    """
    # === Setup: Empty PR ===
    pr = PullRequest(
        pr_number=111,
        repository="acme/webapp",
        title="Update README",
        description="Documentation update",
        author="charlie",
        source_branch="docs/readme",
        target_branch="main",
    )
    # No diff hunks added!
    
    mock_vcs_repository.get_pull_request.return_value = pr
    mock_vcs_repository.get_diff_hunks.return_value = []
    
    config = ProjectConfig(
        global_rules=[
            RuleSet(name="quality", enabled=True, rules_text="Check quality")
        ]
    )
    mock_config_repository.load_config.return_value = config
    
    mock_embedding_store.index_review_history.return_value = None
    
    # === Execute ===
    use_case = ProcessPullRequestUseCase(
        vcs_repository=mock_vcs_repository,
        llm_provider=mock_llm_provider,
        embedding_store=mock_embedding_store,
        config_repository=mock_config_repository,
        static_analyzer=None,
    )
    
    request = PRReviewRequest(repository="acme/webapp", pr_number=111)
    result = await use_case.execute(request)
    
    # === Assertions ===
    assert result.success
    assert result.comment_count == 0, "No comments for empty PR"
    
    # LLM should NOT be called
    mock_llm_provider.generate_review_comments.assert_not_called()
    
    # But review should still be indexed (for tracking)
    mock_embedding_store.index_review_history.assert_called_once()
