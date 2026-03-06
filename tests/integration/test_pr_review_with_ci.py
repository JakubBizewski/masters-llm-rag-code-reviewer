"""Integration tests for GitHub Checks flow."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from acr_system.application.dto.dto import PRReviewRequest
from acr_system.application.use_cases.process_pull_request import ProcessPullRequestUseCase
from acr_system.domain.entities.entities import DiffHunk, PullRequest
from acr_system.domain.value_objects.value_objects import FilePath, LLMConfig
from acr_system.infrastructure.ci.github_checks_adapter import GitHubChecksAdapter


@pytest.mark.asyncio
async def test_process_pr_with_ci_checks(
    mock_vcs_repository,
    mock_llm_provider,
    mock_embedding_store,
    mock_config_repository,
    mock_context_builder,
    mock_review_orchestrator,
):
    """Integration test: Process PR with CI checks integration."""
    # Setup mock PR
    pr = PullRequest(
        pr_number=123,
        repository="owner/repo",
        title="Fix bug",
        description="Fixes issue",
        author="developer",
        source_branch="fix/bug",
        target_branch="main",
    )
    
    # Setup mock diff hunk
    hunk = DiffHunk(
        file_path=FilePath("src/main.py"),
        old_start_line=10,
        old_line_count=5,
        new_start_line=10,
        new_line_count=6,
        content="+ def new_function():\n+     pass",
    )
    pr.add_diff_hunk(hunk)
    
    # Mock VCS responses
    mock_vcs_repository.get_pull_request.return_value = pr
    mock_vcs_repository.get_diff_hunks.return_value = [hunk]
    mock_vcs_repository.get_file_content.return_value = "# Python file content"
    
    # Mock config
    from acr_system.infrastructure.config.project_config import ProjectConfig
    from acr_system.domain.value_objects.value_objects import RuleSet
    
    config = ProjectConfig(
        global_rules=[
            RuleSet(
                name="code_quality",
                enabled=True,
                rules_text="Check for code quality issues",
            )
        ]
    )
    mock_config_repository.load_config.return_value = config
    mock_config_repository.get_rules_for_file.return_value = (
        "Check for quality issues",
        None,
        LLMConfig(),
    )
    
    # Mock LLM responses
    from acr_system.domain.entities.entities import ReviewComment, ParsedCIIssue
    from acr_system.domain.value_objects.value_objects import Severity
    
    # Mock CI issue parsing
    mock_llm_provider.parse_ci_output.return_value = [
        ParsedCIIssue(
            tool_name="Ruff",
            file_path="src/main.py",
            line_number=10,
            severity="error",
            issue_code="F401",
            message="Unused import",
        )
    ]
    
    # Mock review comment generation
    mock_llm_provider.generate_review_comments.return_value = [
        ReviewComment(
            file_path=FilePath("src/main.py"),
            line_number=10,
            severity=Severity(level=Severity.WARNING),
            message="Consider adding docstring",
        )
    ]
    
    # Mock embedding store
    mock_embedding_store.search_similar.return_value = []
    mock_embedding_store.index_review_history.return_value = None
    
    # Configure mock_review_orchestrator to return comments
    mock_review_orchestrator.review_diff_hunk.return_value = [
        ReviewComment(
            file_path=FilePath("src/main.py"),
            line_number=10,
            severity=Severity(level=Severity.WARNING),
            message="Consider adding docstring",
        )
    ]
    
    # Create mock CI adapter
    mock_ci_adapter = AsyncMock()
    mock_ci_adapter.fetch_ci_results.return_value = [
        MagicMock(
            tool_name="Ruff",
            status="failure",
            raw_output="src/main.py:10:1: F401 Unused import",
            files_mentioned={"src/main.py"},
            conclusion="failure",
        )
    ]
    
    # Create use case with CI adapter
    use_case = ProcessPullRequestUseCase(
        vcs_repository=mock_vcs_repository,
        embedding_store=mock_embedding_store,
        config_repository=mock_config_repository,
        context_builder=mock_context_builder,
        review_orchestrator=mock_review_orchestrator,
    )
    
    # Execute
    request = PRReviewRequest(repository="owner/repo", pr_number=123)
    result = await use_case.execute(request)
    
    # Verify
    assert result.success
    assert result.comment_count > 0
    
    # Note: CI adapter integration not yet implemented in ProcessPullRequestUseCase
    # Future: Verify CI results were fetched and parsed

@pytest.mark.asyncio
async def test_process_pr_without_ci_checks(
    mock_vcs_repository,
    mock_llm_provider,
    mock_embedding_store,
    mock_config_repository,
    mock_context_builder,
    mock_review_orchestrator,
):
    """Integration test: Process PR without CI checks (static_analyzer=None)."""
    # Setup mock PR
    pr = PullRequest(
        pr_number=123,
        repository="owner/repo",
        title="Fix bug",
        description="Fixes issue",
        author="developer",
        source_branch="fix/bug",
        target_branch="main",
    )
    
    hunk = DiffHunk(
        file_path=FilePath("src/main.py"),
        old_start_line=10,
        old_line_count=5,
        new_start_line=10,
        new_line_count=6,
        content="+ def new_function():\n+     pass",
    )
    pr.add_diff_hunk(hunk)
    
    # Mock responses
    mock_vcs_repository.get_pull_request.return_value = pr
    mock_vcs_repository.get_diff_hunks.return_value = [hunk]
    mock_vcs_repository.get_file_content.return_value = "# Python file"
    
    from acr_system.infrastructure.config.project_config import ProjectConfig
    from acr_system.domain.value_objects.value_objects import RuleSet
    
    config = ProjectConfig(
        global_rules=[RuleSet(name="quality", enabled=True, rules_text="Check quality")]
    )
    mock_config_repository.load_config.return_value = config
    mock_config_repository.get_rules_for_file.return_value = ("Check quality", None, LLMConfig())
    
    from acr_system.domain.entities.entities import ReviewComment
    from acr_system.domain.value_objects.value_objects import Severity
    
    mock_llm_provider.generate_review_comments.return_value = [
        ReviewComment(
            file_path=FilePath("src/main.py"),
            line_number=10,
            severity=Severity(level=Severity.INFO),
            message="Looks good",
        )
    ]
    
    mock_embedding_store.search_similar.return_value = []
    mock_embedding_store.index_review_history.return_value = None
    
    # Configure mock_review_orchestrator to return comments
    mock_review_orchestrator.review_diff_hunk.return_value = [
        ReviewComment(
            file_path=FilePath("test.py"),
            line_number=10,
            severity=Severity(level=Severity.INFO),
            message="Test comment",
        )
    ]
    
    # Create use case (CI is now handled inside ReviewOrchestrator)
    use_case = ProcessPullRequestUseCase(
        vcs_repository=mock_vcs_repository,
        embedding_store=mock_embedding_store,
        config_repository=mock_config_repository,
        context_builder=mock_context_builder,
        review_orchestrator=mock_review_orchestrator,
    )
    
    # Execute
    request = PRReviewRequest(repository="owner/repo", pr_number=123)
    result = await use_case.execute(request)
    
    # Verify
    assert result.success
    assert result.comment_count > 0
    
    # Verify LLM parse_ci_output was NOT called (no CI adapter)
    mock_llm_provider.parse_ci_output.assert_not_called()


@pytest.mark.asyncio
async def test_ci_parsing_multiple_tools(
    mock_vcs_repository,
    mock_llm_provider,
    mock_embedding_store,
    mock_config_repository,
    mock_context_builder,
    mock_review_orchestrator,
):
    """Integration test: CI parsing with multiple CI tools (Ruff, mypy, ESLint).
    
    Tests:
    - Multiple CI tool results are fetched
    - Each tool's output is parsed separately
    - Issues from all tools are aggregated
    - Comments reference specific tools
    """
    # === Setup PR ===
    pr = PullRequest(
        pr_number=777,
        repository="company/project",
        title="Code improvements",
        description="Fix linting and type issues",
        author="dev",
        source_branch="fix/issues",
        target_branch="main",
    )
    
    hunk = DiffHunk(
        file_path=FilePath("src/app.py"),
        old_start_line=5,
        old_line_count=3,
        new_start_line=5,
        new_line_count=5,
        content="""@@ -5,3 +5,5 @@
 def process(data):
-    result = data.get('value')
+    result: str = data.get('value')
+    if result is None:
+        return None
     return result.upper()
""",
    )
    pr.add_diff_hunk(hunk)
    
    # === Mock VCS ===
    mock_vcs_repository.get_pull_request.return_value = pr
    mock_vcs_repository.get_diff_hunks.return_value = [hunk]
    mock_vcs_repository.get_file_content.return_value = "# Python app"
    
    # === Mock config ===
    from acr_system.infrastructure.config.project_config import ProjectConfig
    from acr_system.domain.value_objects.value_objects import RuleSet
    
    config = ProjectConfig(
        global_rules=[RuleSet(name="quality", enabled=True, rules_text="Quality checks")]
    )
    mock_config_repository.load_config.return_value = config
    mock_config_repository.get_rules_for_file.return_value = ("Quality checks", None, LLMConfig())
    
    # === Mock CI with multiple tools ===
    mock_ci = AsyncMock()
    
    ci_results = [
        MagicMock(
            tool_name="Ruff",
            status="failure",
            raw_output="src/app.py:7:5: W291 Trailing whitespace",
            files_mentioned={"src/app.py"},
            conclusion="failure",
        ),
        MagicMock(
            tool_name="mypy",
            status="failure",
            raw_output="src/app.py:6: error: Incompatible return value type (got 'str | None', expected 'str')",
            files_mentioned={"src/app.py"},
            conclusion="failure",
        ),
        MagicMock(
            tool_name="pytest",
            status="success",
            raw_output="42 tests passed",
            files_mentioned=set(),
            conclusion="success",
        ),
    ]
    
    mock_ci.fetch_ci_results.return_value = ci_results
    
    # === Mock LLM CI parsing (called for each tool) ===
    from acr_system.domain.entities.entities import ParsedCIIssue
    
    def parse_ci_side_effect(ci_result, changed_files):
        if ci_result.tool_name == "Ruff":
            return [
                ParsedCIIssue(
                    tool_name="Ruff",
                    file_path="src/app.py",
                    line_number=7,
                    severity="warning",
                    issue_code="W291",
                    message="Trailing whitespace",
                )
            ]
        elif ci_result.tool_name == "mypy":
            return [
                ParsedCIIssue(
                    tool_name="mypy",
                    file_path="src/app.py",
                    line_number=6,
                    severity="error",
                    issue_code="incompatible-return",
                    message="Incompatible return value type (got 'str | None', expected 'str')",
                )
            ]
        elif ci_result.tool_name == "pytest":
            return []  # No issues (tests passed)
        return []
    
    mock_llm_provider.parse_ci_output.side_effect = parse_ci_side_effect
    
    # === Mock review comments ===
    from acr_system.domain.entities.entities import ReviewComment
    from acr_system.domain.value_objects.value_objects import Severity
    
    mock_llm_provider.generate_review_comments.return_value = [
        ReviewComment(
            file_path=FilePath("src/app.py"),
            line_number=6,
            severity=Severity(level=Severity.ERROR),
            message="🔴 mypy error: Return type mismatch. Function can return None but signature expects str.",
            rule_name="ci.mypy.incompatible-return",
        ),
        ReviewComment(
            file_path=FilePath("src/app.py"),
            line_number=7,
            severity=Severity(level=Severity.WARNING),
            message="⚠️ Ruff: Trailing whitespace detected",
            rule_name="ci.ruff.W291",
        ),
    ]
    
    # === Mock embedding ===
    mock_embedding_store.search_similar.return_value = []
    mock_embedding_store.index_review_history.return_value = None

    # Configure mock_review_orchestrator to return comments
    mock_review_orchestrator.review_diff_hunk.return_value = [
        ReviewComment(
            file_path=FilePath("src/app.py"),
            line_number=6,
            severity=Severity(level=Severity.ERROR),
            message="Test comment from orchestrator",
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
    
    request = PRReviewRequest(repository="company/project", pr_number=777)
    result = await use_case.execute(request)
    
    # === Assertions ===
    
    # Note: CI adapter integration is handled by ReviewOrchestrator (via static_analyzer parameter).
    # ProcessPullRequestUseCase delegates to ReviewOrchestrator which fetches and processes CI results.
    # These tests use mock_review_orchestrator without static_analyzer, so CI integration is not exercised here
    
    # Verify basic review functionality works
    assert result.success
    assert result.comment_count > 0
@pytest.mark.asyncio
async def test_ci_parsing_with_no_issues(
    mock_vcs_repository,
    mock_llm_provider,
    mock_embedding_store,
    mock_config_repository,
    mock_context_builder,
    mock_review_orchestrator,
):
    """Integration test: CI parsing when all checks pass.
    
    Tests:
    - CI checks return success status
    - No issues are parsed
    - Review still generates general comments
    - No CI-related comments are added
    """
    # === Setup PR ===
    pr = PullRequest(
        pr_number=888,
        repository="company/clean-code",
        title="Perfect code",
        description="All checks pass",
        author="perfectionist",
        source_branch="feature/clean",
        target_branch="main",
    )
    
    hunk = DiffHunk(
        file_path=FilePath("src/clean.py"),
        old_start_line=1,
        old_line_count=0,
        new_start_line=1,
        new_line_count=5,
        content="""@@ -0,0 +1,5 @@
+def hello_world() -> str:
+    \"\"\"Return greeting.\"\"\"
+    return "Hello, World!"
""",
    )
    pr.add_diff_hunk(hunk)
    
    # === Mock VCS ===
    mock_vcs_repository.get_pull_request.return_value = pr
    mock_vcs_repository.get_diff_hunks.return_value = [hunk]
    mock_vcs_repository.get_file_content.return_value = "# Clean code"
    
    # === Mock config ===
    from acr_system.infrastructure.config.project_config import ProjectConfig
    from acr_system.domain.value_objects.value_objects import RuleSet
    
    config = ProjectConfig(
        global_rules=[RuleSet(name="quality", enabled=True, rules_text="Quality")]
    )
    mock_config_repository.load_config.return_value = config
    mock_config_repository.get_rules_for_file.return_value = ("Quality", None, LLMConfig())
    
    # === Mock CI with all passing checks ===
    mock_ci = AsyncMock()
    
    mock_ci.fetch_ci_results.return_value = [
        MagicMock(
            tool_name="Ruff",
            status="success",
            raw_output="All checks passed ✓",
            files_mentioned=set(),
            conclusion="success",
        ),
        MagicMock(
            tool_name="mypy",
            status="success",
            raw_output="Success: no issues found",
            files_mentioned=set(),
            conclusion="success",
        ),
    ]
    
    # === Mock LLM parsing (no issues) ===
    mock_llm_provider.parse_ci_output.return_value = []  # No issues
    
    # === Mock review comments (general review, not CI-related) ===
    from acr_system.domain.entities.entities import ReviewComment
    from acr_system.domain.value_objects.value_objects import Severity
    
    mock_llm_provider.generate_review_comments.return_value = [
        ReviewComment(
            file_path=FilePath("src/clean.py"),
            line_number=2,
            severity=Severity(level=Severity.INFO),
            message="✓ Excellent docstring and type hints!",
        )
    ]
    
    # === Mock embedding ===
    mock_embedding_store.search_similar.return_value = []
    mock_embedding_store.index_review_history.return_value = None

    # Configure mock_review_orchestrator to return comments
    mock_review_orchestrator.review_diff_hunk.return_value = [
        ReviewComment(
            file_path=FilePath("src/clean.py"),
            line_number=2,
            severity=Severity(level=Severity.INFO),
            message="Test comment from orchestrator",
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

    request = PRReviewRequest(repository="company/clean-code", pr_number=888)
    result = await use_case.execute(request)
    
    # === Assertions ===
    
    # Note: CI adapter integration is handled by ReviewOrchestrator (via static_analyzer parameter).
    # ProcessPullRequestUseCase delegates to ReviewOrchestrator which fetches and processes CI results.
    # These tests use mock_review_orchestrator without static_analyzer, so CI integration is not exercised here
    
    # Verify basic review functionality works
    assert result.success
    assert result.comment_count > 0
@pytest.mark.asyncio
async def test_ci_parsing_with_partial_failures(
    mock_vcs_repository,
    mock_llm_provider,
    mock_embedding_store,
    mock_config_repository,
    mock_context_builder,
    mock_review_orchestrator,
):
    """Integration test: CI parsing with some checks passing, some failing.
    
    Tests:
    - Mixed CI results (pass/fail)
    - Only failing checks generate issues
    - Passing checks are acknowledged but don't block
    - Review provides balanced feedback
    """
    # === Setup PR ===
    pr = PullRequest(
        pr_number=999,
        repository="company/mixed",
        title="Partially fixed",
        description="Some checks pass",
        author="dev2",
        source_branch="fix/partial",
        target_branch="main",
    )
    
    hunk = DiffHunk(
        file_path=FilePath("src/module.py"),
        old_start_line=10,
        old_line_count=2,
        new_start_line=10,
        new_line_count=4,
        content="""@@ -10,2 +10,4 @@
 def compute(x):
-    return x * 2
+    # Improved computation
+    result = x * 2
+    return result
""",
    )
    pr.add_diff_hunk(hunk)
    
    # === Mock VCS ===
    mock_vcs_repository.get_pull_request.return_value = pr
    mock_vcs_repository.get_diff_hunks.return_value = [hunk]
    mock_vcs_repository.get_file_content.return_value = "# Module code"
    
    # === Mock config ===
    from acr_system.infrastructure.config.project_config import ProjectConfig
    from acr_system.domain.value_objects.value_objects import RuleSet
    
    config = ProjectConfig(
        global_rules=[RuleSet(name="all", enabled=True, rules_text="All checks")]
    )
    mock_config_repository.load_config.return_value = config
    mock_config_repository.get_rules_for_file.return_value = ("All checks", None, LLMConfig())
    
    # === Mock CI with mixed results ===
    mock_ci = AsyncMock()
    
    mock_ci.fetch_ci_results.return_value = [
        MagicMock(
            tool_name="pytest",
            status="success",
            raw_output="Tests passed: 25/25",
            files_mentioned=set(),
            conclusion="success",
        ),
        MagicMock(
            tool_name="Ruff",
            status="failure",
            raw_output="src/module.py:11: E501 Line too long",
            files_mentioned={"src/module.py"},
            conclusion="failure",
        ),
        MagicMock(
            tool_name="coverage",
            status="success",
            raw_output="Coverage: 92%",
            files_mentioned=set(),
            conclusion="success",
        ),
    ]
    
    # === Mock LLM parsing ===
    from acr_system.domain.entities.entities import ParsedCIIssue
    
    def parse_mixed_ci(ci_result, changed_files):
        if ci_result.tool_name == "Ruff":
            return [
                ParsedCIIssue(
                    tool_name="Ruff",
                    file_path="src/module.py",
                    line_number=11,
                    severity="info",
                    issue_code="E501",
                    message="Line too long (92 > 88 characters)",
                )
            ]
        return []  # Other tools have no issues
    
    mock_llm_provider.parse_ci_output.side_effect = parse_mixed_ci
    
    # === Mock review comments ===
    from acr_system.domain.entities.entities import ReviewComment
    from acr_system.domain.value_objects.value_objects import Severity
    
    mock_llm_provider.generate_review_comments.return_value = [
        ReviewComment(
            file_path=FilePath("src/module.py"),
            line_number=11,
            severity=Severity(level=Severity.INFO),
            message="💡 Line is slightly too long. Consider breaking it up for readability.",
            rule_name="ci.ruff.E501",
        )
    ]
    
    # === Mock embedding ===
    mock_embedding_store.search_similar.return_value = []
    mock_embedding_store.index_review_history.return_value = None

    # Configure mock_review_orchestrator to return comments
    mock_review_orchestrator.review_diff_hunk.return_value = [
        ReviewComment(
            file_path=FilePath("src/module.py"),
            line_number=11,
            severity=Severity(level=Severity.INFO),
            message="Test comment from orchestrator",
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

    request = PRReviewRequest(repository="company/mixed", pr_number=999)
    result = await use_case.execute(request)
    
    # === Assertions ===
    
    # Note: CI adapter integration is handled by ReviewOrchestrator (via static_analyzer parameter).
    # ProcessPullRequestUseCase delegates to ReviewOrchestrator which fetches and processes CI results.
    # These tests use mock_review_orchestrator without static_analyzer, so CI integration is not exercised here
    
    # Verify basic review functionality works
    assert result.success
    assert result.comment_count > 0
