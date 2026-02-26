"""Integration tests for GitHub Checks flow."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from acr_system.application.dto.dto import PRReviewRequest
from acr_system.application.use_cases.process_pull_request import ProcessPullRequestUseCase
from acr_system.domain.entities.entities import DiffHunk, PullRequest
from acr_system.domain.value_objects.value_objects import FilePath
from acr_system.infrastructure.ci.github_checks_adapter import GitHubChecksAdapter


@pytest.mark.asyncio
async def test_process_pr_with_ci_checks(
    mock_vcs_repository,
    mock_llm_provider,
    mock_embedding_store,
    mock_config_repository,
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
        llm_provider=mock_llm_provider,
        embedding_store=mock_embedding_store,
        config_repository=mock_config_repository,
        static_analyzer=mock_ci_adapter,
    )
    
    # Execute
    request = PRReviewRequest(repository="owner/repo", pr_number=123)
    result = await use_case.execute(request)
    
    # Verify
    assert result.success
    assert result.comment_count > 0
    
    # Verify CI results were fetched
    mock_ci_adapter.fetch_ci_results.assert_called_once()
    
    # Verify LLM was called to parse CI output
    mock_llm_provider.parse_ci_output.assert_called_once()
    
    # Verify LLM was called to generate review comments
    mock_llm_provider.generate_review_comments.assert_called_once()
    
    # Verify review was indexed for RAG
    mock_embedding_store.index_review_history.assert_called_once()


@pytest.mark.asyncio
async def test_process_pr_without_ci_checks(
    mock_vcs_repository,
    mock_llm_provider,
    mock_embedding_store,
    mock_config_repository,
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
    mock_config_repository.get_rules_for_file.return_value = ("Check quality", None)
    
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
    
    # Create use case WITHOUT CI adapter
    use_case = ProcessPullRequestUseCase(
        vcs_repository=mock_vcs_repository,
        llm_provider=mock_llm_provider,
        embedding_store=mock_embedding_store,
        config_repository=mock_config_repository,
        static_analyzer=None,  # No CI checks
    )
    
    # Execute
    request = PRReviewRequest(repository="owner/repo", pr_number=123)
    result = await use_case.execute(request)
    
    # Verify
    assert result.success
    assert result.comment_count > 0
    
    # Verify LLM parse_ci_output was NOT called (no CI adapter)
    mock_llm_provider.parse_ci_output.assert_not_called()
