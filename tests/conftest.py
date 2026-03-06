"""Pytest configuration and fixtures."""
import pytest
from unittest.mock import AsyncMock, MagicMock, Mock

from acr_system.domain.entities.entities import DiffHunk, PullRequest
from acr_system.domain.value_objects.value_objects import FilePath


@pytest.fixture
def sample_diff_hunk() -> DiffHunk:
    """Fixture for a sample diff hunk."""
    return DiffHunk(
        file_path=FilePath("src/main.py"),
        old_start_line=10,
        old_line_count=5,
        new_start_line=10,
        new_line_count=6,
        content="""@@ -10,5 +10,6 @@
 def hello():
-    print("Hello")
+    print("Hello, World!")
+    return True
""",
    )


@pytest.fixture
def sample_pull_request() -> PullRequest:
    """Fixture for a sample pull request."""
    return PullRequest(
        pr_number=123,
        repository="owner/repo",
        title="Add greeting function",
        description="This PR adds a new greeting function",
        author="john_doe",
        source_branch="feature/greeting",
        target_branch="main",
    )


@pytest.fixture
def mock_vcs_repository() -> AsyncMock:
    """Fixture for a mock VCS repository."""
    mock = AsyncMock()
    mock.get_pull_request = AsyncMock()
    mock.get_diff_hunks = AsyncMock()
    mock.post_review_comment = AsyncMock()
    mock.post_review_comments = AsyncMock()
    mock.get_file_content = AsyncMock()
    return mock


@pytest.fixture
def mock_llm_provider() -> AsyncMock:
    """Fixture for a mock LLM provider."""
    mock = AsyncMock()
    mock.generate_review_comments = AsyncMock()
    mock.parse_ci_output = AsyncMock()
    mock.generate_completion = AsyncMock()
    # Also act as factory for tests (returns self)
    mock.create_provider = MagicMock(return_value=mock)
    return mock


@pytest.fixture
def mock_embedding_store() -> AsyncMock:
    """Fixture for a mock embedding store."""
    mock = AsyncMock()
    mock.index_documents = AsyncMock()
    mock.search_similar = AsyncMock()
    mock.index_review_history = AsyncMock()
    return mock


@pytest.fixture
def mock_config_repository() -> AsyncMock:
    """Fixture for a mock config repository."""
    mock = AsyncMock()
    mock.load_config = AsyncMock()
    mock.get_rules_for_file = AsyncMock()
    return mock


@pytest.fixture
def mock_ast_parser() -> AsyncMock:
    """Fixture for a mock AST parser."""
    mock = AsyncMock()
    mock.parse_file = AsyncMock()
    mock.extract_functions = AsyncMock()
    mock.extract_classes = AsyncMock()
    mock.extract_imports = AsyncMock()
    return mock


@pytest.fixture
def mock_context_builder() -> AsyncMock:
    """Fixture for a mock context builder."""
    mock = AsyncMock()
    mock.build_context = AsyncMock()
    return mock


@pytest.fixture
def mock_review_orchestrator() -> AsyncMock:
    """Fixture for a mock review orchestrator."""
    mock = AsyncMock()
    mock.review_pull_request = AsyncMock()
    mock.review_diff_hunk = AsyncMock()
    return mock
