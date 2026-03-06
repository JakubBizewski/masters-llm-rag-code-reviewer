"""Tests for GitHub Checks Adapter."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from acr_system.infrastructure.auth.github_jwt import GitHubAppAuth
from acr_system.infrastructure.ci.github_checks_adapter import GitHubChecksAdapter
from acr_system.shared.exceptions.infrastructure_exceptions import CIFetchError


@pytest.fixture
def mock_auth():
    """Fixture for mock GitHubAppAuth."""
    auth = MagicMock(spec=GitHubAppAuth)
    auth.get_auth_headers = AsyncMock(return_value={
        "Authorization": "Bearer test-token",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    return auth


@pytest.fixture
def github_checks_adapter(mock_auth):
    """Fixture for GitHubChecksAdapter."""
    return GitHubChecksAdapter(auth=mock_auth)


@pytest.fixture
def mock_check_run():
    """Fixture for a mock check run response."""
    return {
        "id": 12345,
        "name": "Ruff",
        "status": "completed",
        "conclusion": "failure",
        "output": {
            "title": "Linting failed",
            "summary": "Found 3 issues",
            "text": "src/main.py:10:1: F401 Unused import\nsrc/utils.py:20:5: E501 Line too long",
        },
    }


@pytest.fixture
def mock_annotations():
    """Fixture for mock annotations."""
    return [
        {
            "path": "src/main.py",
            "start_line": 10,
            "end_line": 10,
            "annotation_level": "failure",
            "message": "F401: Unused import 'typing'",
        },
        {
            "path": "src/utils.py",
            "start_line": 20,
            "end_line": 20,
            "annotation_level": "warning",
            "message": "E501: Line too long (92 > 88 characters)",
        },
    ]


class TestGitHubChecksAdapter:
    """Tests for GitHubChecksAdapter."""
    
    @pytest.mark.asyncio
    async def test_fetch_ci_results_success(self, github_checks_adapter, mock_check_run):
        """Test fetching CI results for a PR."""
        # Mock PR response
        pr_response = MagicMock()
        pr_response.json.return_value = {
            "head": {"sha": "abc123"}
        }
        pr_response.raise_for_status = MagicMock()
        
        # Mock check runs response
        check_runs_response = MagicMock()
        check_runs_response.json.return_value = {
            "check_runs": [mock_check_run]
        }
        check_runs_response.raise_for_status = MagicMock()
        
        # Mock annotations response (empty)
        annotations_response = MagicMock()
        annotations_response.status_code = 404
        
        with patch.object(github_checks_adapter.client, 'get') as mock_get:
            mock_get.side_effect = [pr_response, check_runs_response, annotations_response]
            
            results = await github_checks_adapter.fetch_ci_results(
                repo="owner/repo",
                pr_number=123,
            )
            
            assert len(results) == 1
            assert results[0].tool_name == "Ruff"
            assert results[0].status == "failure"
            assert results[0].conclusion == "failure"
            assert "F401" in results[0].raw_output
    
    @pytest.mark.asyncio
    async def test_get_check_runs_multiple(self, github_checks_adapter):
        """Test getting multiple check runs."""
        check_runs = [
            {
                "id": 1,
                "name": "Ruff",
                "status": "completed",
                "conclusion": "failure",
                "output": {"title": "Linting failed", "summary": "Issues found", "text": ""},
            },
            {
                "id": 2,
                "name": "MyPy",
                "status": "completed",
                "conclusion": "failure",
                "output": {"title": "Type errors", "summary": "Type issues", "text": ""},
            },
            {
                "id": 3,
                "name": "Tests",
                "status": "completed",
                "conclusion": "success",
                "output": {"title": "All tests passed", "summary": "OK", "text": ""},
            },
        ]
        
        response = MagicMock()
        response.json.return_value = {"check_runs": check_runs}
        response.raise_for_status = MagicMock()
        
        annotations_response = MagicMock()
        annotations_response.status_code = 404
        
        with patch.object(github_checks_adapter.client, 'get') as mock_get:
            mock_get.side_effect = [response] + [annotations_response] * 3
            
            results = await github_checks_adapter.get_check_runs(
                repo="owner/repo",
                commit_sha="abc123",
            )
            
            # Should only return failed checks (not success)
            assert len(results) == 2
            assert results[0].tool_name == "Ruff"
            assert results[1].tool_name == "MyPy"
    
    @pytest.mark.asyncio
    async def test_parse_check_run_with_annotations(
        self,
        github_checks_adapter,
        mock_check_run,
        mock_annotations,
    ):
        """Test parsing check run with annotations."""
        annotations_response = MagicMock()
        annotations_response.json.return_value = mock_annotations
        annotations_response.raise_for_status = MagicMock()
        
        with patch.object(github_checks_adapter.client, 'get', return_value=annotations_response):
            result = await github_checks_adapter._parse_check_run(
                check_run=mock_check_run,
                repo="owner/repo",
                commit_sha="abc123",
            )
            
            assert result is not None
            assert result.tool_name == "Ruff"
            assert "src/main.py" in result.files_mentioned
            assert "src/utils.py" in result.files_mentioned
            assert "F401" in result.raw_output
            assert "E501" in result.raw_output
    
    @pytest.mark.asyncio
    async def test_parse_check_run_skips_in_progress(self, github_checks_adapter):
        """Test that in-progress check runs are skipped."""
        check_run = {
            "id": 1,
            "name": "Ruff",
            "status": "in_progress",
            "conclusion": None,
            "output": {},
        }
        
        result = await github_checks_adapter._parse_check_run(
            check_run=check_run,
            repo="owner/repo",
            commit_sha="abc123",
        )
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_parse_check_run_skips_success(self, github_checks_adapter):
        """Test that successful check runs are skipped."""
        check_run = {
            "id": 1,
            "name": "Tests",
            "status": "completed",
            "conclusion": "success",
            "output": {"title": "All tests passed", "summary": "", "text": ""},
        }
        
        result = await github_checks_adapter._parse_check_run(
            check_run=check_run,
            repo="owner/repo",
            commit_sha="abc123",
        )
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_fetch_annotations_not_found(self, github_checks_adapter):
        """Test fetching annotations when endpoint returns 404."""
        response = MagicMock()
        response.status_code = 404
        
        with patch.object(github_checks_adapter.client, 'get', return_value=response):
            annotations = await github_checks_adapter._fetch_annotations(
                check_run_id=12345,
                repo="owner/repo",
            )
            
            assert annotations == []
    
    @pytest.mark.asyncio
    async def test_fetch_ci_results_http_error(self, github_checks_adapter):
        """Test error handling when GitHub API returns error."""
        import httpx
        
        with patch.object(github_checks_adapter.client, 'get') as mock_get:
            mock_get.side_effect = httpx.HTTPError("API error")
            
            with pytest.raises(CIFetchError, match="Error fetching CI results"):
                await github_checks_adapter.fetch_ci_results(
                    repo="owner/repo",
                    pr_number=123,
                )
    
    @pytest.mark.asyncio
    async def test_close(self, github_checks_adapter):
        """Test closing the HTTP client."""
        with patch.object(github_checks_adapter.client, 'aclose') as mock_close:
            await github_checks_adapter.close()
            mock_close.assert_called_once()

