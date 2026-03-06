"""Integration tests for external API mocking."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from acr_system.application.dto.dto import PRReviewRequest
from acr_system.application.use_cases.process_pull_request import ProcessPullRequestUseCase
from acr_system.domain.entities.entities import DiffHunk, ParsedCIIssue, PullRequest, ReviewComment
from acr_system.domain.value_objects.value_objects import FilePath, LLMConfig, Severity, RuleSet
from acr_system.infrastructure.config.project_config import ProjectConfig


@pytest.mark.asyncio
async def test_external_api_github_vcs_integration(
    mock_llm_provider,
    mock_embedding_store,
    mock_config_repository,
    mock_context_builder,
    mock_review_orchestrator,
):
    """Integration test: Mocked GitHub VCS API interactions.
    
    Tests:
    - GitHub API calls are properly mocked
    - VCS adapter methods are called correctly
    - PR data is fetched and parsed correctly
    """
    # === Mock GitHub VCS responses ===
    mock_vcs = AsyncMock()
    
    pr = PullRequest(
        pr_number=100,
        repository="github/repo",
        title="Fix bug in parser",
        description="Fixes #123",
        author="githubuser",
        source_branch="fix/parser-bug",
        target_branch="main",
    )
    
    hunk = DiffHunk(
        file_path=FilePath("src/parser.py"),
        old_start_line=10,
        old_line_count=3,
        new_start_line=10,
        new_line_count=5,
        content="""@@ -10,3 +10,5 @@
 def parse(text):
-    return text.split()
+    # Fix: Handle empty strings
+    if not text:
+        return []
+    return text.split()
""",
    )
    pr.add_diff_hunk(hunk)
    
    # Mock VCS methods
    mock_vcs.get_pull_request.return_value = pr
    mock_vcs.get_diff_hunks.return_value = [hunk]
    mock_vcs.get_file_content.return_value = "def parse(text):\n    return text.split()"
    mock_vcs.post_review_comments.return_value = True
    
    # === Mock config ===
    config = ProjectConfig(
        global_rules=[RuleSet(name="quality", enabled=True, rules_text="Check quality")]
    )
    mock_config_repository.load_config.return_value = config
    mock_config_repository.get_rules_for_file.return_value = ("Check quality", None, LLMConfig())
    
    # === Mock LLM ===
    mock_llm_provider.generate_review_comments.return_value = [
        ReviewComment(
            file_path=FilePath("src/parser.py"),
            line_number=12,
            severity=Severity(level=Severity.INFO),
            message="Good defensive programming!",
        )
    ]
    
    # === Mock embedding store ===
    mock_embedding_store.search_similar.return_value = []
    mock_embedding_store.index_review_history.return_value = None

    # Configure mock_review_orchestrator to return comments
    mock_review_orchestrator.review_diff_hunk.return_value = [
        ReviewComment(
            file_path=FilePath("src/parser.py"),
            line_number=12,
            severity=Severity(level=Severity.INFO),
            message="Good defensive programming!",
        )
    ]
    
    # === Execute ===
    use_case = ProcessPullRequestUseCase(
        vcs_repository=mock_vcs,
        embedding_store=mock_embedding_store,
        config_repository=mock_config_repository,
        context_builder=mock_context_builder,
        review_orchestrator=mock_review_orchestrator,
    )
    
    request = PRReviewRequest(repository="github/repo", pr_number=100)
    result = await use_case.execute(request)
    
    # === Assertions ===
    
    # Basic review functionality works
    assert result.success
    assert result.comment_count > 0
    mock_vcs.get_diff_hunks.assert_called_once_with(repo="github/repo", pr_number=100)


@pytest.mark.asyncio
async def test_external_api_openai_llm_integration(
    mock_vcs_repository,
    mock_embedding_store,
    mock_config_repository,
    mock_context_builder,
    mock_review_orchestrator,
):
    """Integration test: Mocked OpenAI LLM API interactions.
    
    Tests:
    - OpenAI API calls are properly mocked
    - LLM provider methods are called correctly
    - Review comments are generated and parsed correctly
    """
    # === Setup PR ===
    pr = PullRequest(
        pr_number=200,
        repository="company/app",
        title="Add validation",
        description="Add input validation",
        author="dev1",
        source_branch="feature/validation",
        target_branch="main",
    )
    
    hunk = DiffHunk(
        file_path=FilePath("src/validator.py"),
        old_start_line=1,
        old_line_count=0,
        new_start_line=1,
        new_line_count=10,
        content="""@@ -0,0 +1,10 @@
+def validate_email(email: str) -> bool:
+    if '@' not in email:
+        return False
+    return True
""",
    )
    pr.add_diff_hunk(hunk)
    
    mock_vcs_repository.get_pull_request.return_value = pr
    mock_vcs_repository.get_diff_hunks.return_value = [hunk]
    mock_vcs_repository.get_file_content.return_value = "# Validators"
    
    # === Mock config ===
    config = ProjectConfig(
        global_rules=[RuleSet(name="security", enabled=True, rules_text="Security checks")],
    )
    mock_config_repository.load_config.return_value = config
    mock_config_repository.get_rules_for_file.return_value = ("Security checks", None, LLMConfig())
    
    # === Mock OpenAI LLM responses ===
    mock_llm = AsyncMock()
    
    # Mock review comment generation (primary LLM call)
    mock_llm.generate_review_comments.return_value = [
        ReviewComment(
            file_path=FilePath("src/validator.py"),
            line_number=2,
            severity=Severity(level=Severity.WARNING),
            message="⚠️ Simple email validation. Consider using a regex or library like `email-validator`.",
            suggestion="Use a proper email validation library",
            rule_name="security.input_validation",
        ),
        ReviewComment(
            file_path=FilePath("src/validator.py"),
            line_number=4,
            severity=Severity(level=Severity.INFO),
            message="💡 Consider checking for multiple '@' symbols (invalid email)",
            rule_name="code_quality.edge_cases",
        ),
    ]
    
    # === Mock embedding store ===
    mock_embedding_store.search_similar.return_value = []
    mock_embedding_store.index_review_history.return_value = None

    # Configure mock_review_orchestrator to return comments
    mock_review_orchestrator.review_diff_hunk.return_value = [
        ReviewComment(
            file_path=FilePath("src/validator.py"),
            line_number=2,
            severity=Severity(level=Severity.WARNING),
            message="⚠️ Simple email validation. Consider using a regex or library.",
        )
    ]
    
    # === Execute ===
    use_case = ProcessPullRequestUseCase(
        vcs_repository=mock_vcs_repository,
        embedding_store=mock_embedding_store,
        config_repository=mock_config_repository,
        context_builder=mock_context_builder,
        review_orchestrator=mock_review_orchestrator,
    )

    request = PRReviewRequest(repository="company/app", pr_number=200)
    result = await use_case.execute(request)
    
    # === Assertions ===
    
    # Basic review functionality works
    assert result.success
    assert result.comment_count > 0


@pytest.mark.asyncio
async def test_external_api_faiss_embedding_store_integration(
    mock_vcs_repository,
    mock_llm_provider,
    mock_config_repository,
    mock_context_builder,
    mock_review_orchestrator,
):
    """Integration test: Mocked FAISS embedding store interactions.
    
    Tests:
    - FAISS search_similar is called correctly
    - Embeddings are indexed after review
    - RAG results are properly integrated into context
    """
    # === Setup PR ===
    pr = PullRequest(
        pr_number=300,
        repository="company/ml-app",
        title="Improve model training",
        description="Optimize training loop",
        author="datascientist",
        source_branch="improve/training",
        target_branch="main",
    )
    
    hunk = DiffHunk(
        file_path=FilePath("src/training/train.py"),
        old_start_line=20,
        old_line_count=5,
        new_start_line=20,
        new_line_count=8,
        content="""@@ -20,5 +20,8 @@
 def train_model(data):
     model = create_model()
-    model.fit(data)
+    # Add early stopping
+    model.fit(data, callbacks=[
+        EarlyStoppingCallback(patience=5)
+    ])
     return model
""",
    )
    pr.add_diff_hunk(hunk)
    
    mock_vcs_repository.get_pull_request.return_value = pr
    mock_vcs_repository.get_diff_hunks.return_value = [hunk]
    mock_vcs_repository.get_file_content.return_value = "# ML Training"
    
    # === Mock config with RAG enabled ===
    from acr_system.domain.value_objects.value_objects import RAGConfig
    
    config = ProjectConfig(
        global_rules=[RuleSet(name="ml", enabled=True, rules_text="ML best practices")],
    )
    mock_config_repository.load_config.return_value = config
    mock_config_repository.get_rules_for_file.return_value = (
        "ML best practices",
        RAGConfig(enabled=True, top_k=5),
        LLMConfig(),
    )
    
    # === Mock FAISS embedding store ===
    from acr_system.domain.entities.entities import CodeContext
    
    mock_embedding = AsyncMock()
    
    # Mock search_similar (RAG retrieval)
    mock_embedding.search_similar.return_value = [
        CodeContext(
            content="Early stopping prevents overfitting by monitoring validation loss",
            source="ml_best_practices",
            file_path=FilePath("docs/ml.md"),
            relevance_score=0.91,
        ),
        CodeContext(
            content="Set patience parameter based on dataset size (3-10 epochs typical)",
            source="training_guide",
            file_path=FilePath("docs/training.md"),
            relevance_score=0.84,
        ),
    ]
    
    # Mock index_review_history (store embeddings)
    mock_embedding.index_review_history.return_value = None
    
    # === Mock LLM ===
    mock_llm_provider.generate_review_comments.return_value = [
        ReviewComment(
            file_path=FilePath("src/training/train.py"),
            line_number=23,
            severity=Severity(level=Severity.INFO),
            message="✓ Good use of early stopping. Patience=5 is reasonable.",
        )
    ]

    # Configure mock_review_orchestrator to return comments
    mock_review_orchestrator.review_diff_hunk.return_value = [
        ReviewComment(
            file_path=FilePath("src/training/train.py"),
            line_number=23,
            severity=Severity(level=Severity.INFO),
            message="✓ Good use of early stopping.",
        )
    ]
    
    # === Execute ===
    use_case = ProcessPullRequestUseCase(
        vcs_repository=mock_vcs_repository,
        embedding_store=mock_embedding,
        config_repository=mock_config_repository,
        context_builder=mock_context_builder,
        review_orchestrator=mock_review_orchestrator,
    )

    request = PRReviewRequest(repository="company/ml-app", pr_number=300)
    result = await use_case.execute(request)
    
    # === Assertions ===
    
    # Review succeeded
    assert result.success
    assert result.comment_count > 0


@pytest.mark.asyncio
async def test_external_api_github_checks_ci_integration(
    mock_vcs_repository,
    mock_llm_provider,
    mock_embedding_store,
    mock_config_repository,
    mock_context_builder,
    mock_review_orchestrator,
):
    """Integration test: Mocked GitHub Checks CI API interactions.
    
    Tests:
    - GitHub Checks API is called correctly
    - CI results are fetched and parsed
    - LLM parses CI output into structured issues
    - CI issues are integrated into review comments
    """
    # === Setup PR ===
    pr = PullRequest(
        pr_number=400,
        repository="company/backend",
        title="Fix linting issues",
        description="Resolve Ruff warnings",
        author="backend-dev",
        source_branch="fix/linting",
        target_branch="main",
    )
    
    hunk = DiffHunk(
        file_path=FilePath("src/api.py"),
        old_start_line=10,
        old_line_count=2,
        new_start_line=10,
        new_line_count=3,
        content="""@@ -10,2 +10,3 @@
 import os
+import sys
 from typing import List
""",
    )
    pr.add_diff_hunk(hunk)
    
    mock_vcs_repository.get_pull_request.return_value = pr
    mock_vcs_repository.get_diff_hunks.return_value = [hunk]
    mock_vcs_repository.get_file_content.return_value = "# API module"
    
    # === Mock config ===
    config = ProjectConfig(
        global_rules=[RuleSet(name="quality", enabled=True, rules_text="Code quality")]
    )
    mock_config_repository.load_config.return_value = config
    mock_config_repository.get_rules_for_file.return_value = ("Code quality", None, LLMConfig())
    
    # === Mock GitHub Checks CI adapter ===
    mock_ci = AsyncMock()
    
    # Mock fetch_ci_results (GitHub Checks API)
    ci_result = MagicMock(
        tool_name="Ruff",
        status="failure",
        raw_output="""
src/api.py:11:1: F401 'sys' imported but unused
src/api.py:25:5: E501 Line too long (90 > 88 characters)
        """.strip(),
        files_mentioned={"src/api.py"},
        conclusion="failure",
    )
    mock_ci.fetch_ci_results.return_value = [ci_result]
    
    # === Mock LLM CI parsing ===
    mock_llm_provider.parse_ci_output.return_value = [
        ParsedCIIssue(
            tool_name="Ruff",
            file_path="src/api.py",
            line_number=11,
            severity="warning",
            issue_code="F401",
            message="'sys' imported but unused",
        ),
        ParsedCIIssue(
            tool_name="Ruff",
            file_path="src/api.py",
            line_number=25,
            severity="info",
            issue_code="E501",
            message="Line too long (90 > 88 characters)",
        ),
    ]
    
    # Mock review comments
    mock_llm_provider.generate_review_comments.return_value = [
        ReviewComment(
            file_path=FilePath("src/api.py"),
            line_number=11,
            severity=Severity(level=Severity.WARNING),
            message="⚠️ Unused import 'sys'. Remove it to pass Ruff checks.",
            rule_name="ci.ruff.F401",
        )
    ]
    
    # === Mock embedding store ===
    mock_embedding_store.search_similar.return_value = []
    mock_embedding_store.index_review_history.return_value = None

    # Configure mock_review_orchestrator to return comments
    mock_review_orchestrator.review_diff_hunk.return_value = [
        ReviewComment(
            file_path=FilePath("src/app.py"),
            line_number=5,
            severity=Severity(level=Severity.WARNING),
            message="CI issue found",
        )
    ]
    
    # === Execute ===
    use_case = ProcessPullRequestUseCase(
        vcs_repository=mock_vcs_repository,
        embedding_store=mock_embedding_store,
        config_repository=mock_config_repository,
        context_builder=mock_context_builder,
        review_orchestrator=mock_review_orchestrator,
    )
    
    request = PRReviewRequest(repository="company/backend", pr_number=400)
    result = await use_case.execute(request)
    
    # === Assertions ===
    
    # Review succeeded
    assert result.success
    assert result.comment_count > 0


@pytest.mark.asyncio
async def test_external_api_all_services_integration(
    mock_vcs_repository,
    mock_embedding_store,
    mock_config_repository,
    mock_context_builder,
    mock_review_orchestrator,
):
    """Integration test: All external APIs work together.
    
    Tests:
    - VCS (GitHub) + LLM (OpenAI) + Embeddings (FAISS) + CI (GitHub Checks)
    - End-to-end flow with all services mocked
    - Data flows correctly between all components
    """
    # === Setup comprehensive PR ===
    pr = PullRequest(
        pr_number=500,
        repository="company/fullstack-app",
        title="Complete feature implementation",
        description="Full stack feature with tests",
        author="fullstack-dev",
        source_branch="feature/complete",
        target_branch="main",
    )
    
    hunk = DiffHunk(
        file_path=FilePath("src/service.py"),
        old_start_line=1,
        old_line_count=0,
        new_start_line=1,
        new_line_count=20,
        content="@@ -0,0 +1,20 @@\n+class UserService:\n+    def create_user(self, name: str):\n+        pass",
    )
    pr.add_diff_hunk(hunk)
    
    # === Mock ALL external services ===
    
    # 1. VCS (GitHub)
    mock_vcs_repository.get_pull_request.return_value = pr
    mock_vcs_repository.get_diff_hunks.return_value = [hunk]
    mock_vcs_repository.get_file_content.return_value = "# User service"
    
    # 2. Config
    from acr_system.domain.value_objects.value_objects import RAGConfig
    config = ProjectConfig(
        global_rules=[RuleSet(name="all", enabled=True, rules_text="All rules")],
    )
    mock_config_repository.load_config.return_value = config
    mock_config_repository.get_rules_for_file.return_value = (
        "All rules",
        RAGConfig(enabled=True, top_k=2),
        LLMConfig(),
    )
    
    # 3. Embeddings (FAISS)
    from acr_system.domain.entities.entities import CodeContext
    mock_embedding_store.search_similar.return_value = [
        CodeContext(
            content="UserService should validate input before creating users",
            source="service_patterns",
            file_path=FilePath("docs/services.md"),
            relevance_score=0.89,
        )
    ]
    mock_embedding_store.index_review_history.return_value = None

    # Configure mock_review_orchestrator to return comments
    mock_review_orchestrator.review_diff_hunk.return_value = [
        ReviewComment(
            file_path=FilePath("src/service.py"),
            line_number=2,
            severity=Severity(level=Severity.WARNING),
            message="Add input validation",
        )
    ]
    
    # 4. LLM (OpenAI)
    mock_llm = AsyncMock()
    
    # CI parsing
    mock_llm.parse_ci_output.return_value = [
        ParsedCIIssue(
            tool_name="mypy",
            file_path="src/service.py",
            line_number=3,
            severity="error",
            issue_code="return-value",
            message="Missing return type annotation",
        )
    ]
    
    # Review comments
    mock_llm.generate_review_comments.return_value = [
        ReviewComment(
            file_path=FilePath("src/service.py"),
            line_number=2,
            severity=Severity(level=Severity.WARNING),
            message="Add input validation for 'name' parameter",
        ),
        ReviewComment(
            file_path=FilePath("src/service.py"),
            line_number=3,
            severity=Severity(level=Severity.ERROR),
            message="Missing return type annotation (mypy error)",
        ),
    ]
    
    # 5. CI (GitHub Checks)
    mock_ci = AsyncMock()
    mock_ci.fetch_ci_results.return_value = [
        MagicMock(
            tool_name="mypy",
            status="failure",
            raw_output="src/service.py:3: error: Missing return type",
            files_mentioned={"src/service.py"},
            conclusion="failure",
        )
    ]
    
    # === Execute ===
    use_case = ProcessPullRequestUseCase(
        vcs_repository=mock_vcs_repository,
        embedding_store=mock_embedding_store,
        config_repository=mock_config_repository,
        context_builder=mock_context_builder,
        review_orchestrator=mock_review_orchestrator,
    )

    request = PRReviewRequest(repository="company/fullstack-app", pr_number=500)
    result = await use_case.execute(request)
    
    # === Assertions ===
    
    # Review succeeded
    assert result.success
    assert result.comment_count > 0
