"""Tests for GitLab CI Adapter."""

from unittest.mock import MagicMock, patch

import pytest

from acr_system.infrastructure.ci.gitlab_ci_adapter import GitLabCIAdapter
from acr_system.shared.exceptions.infrastructure_exceptions import CIFetchError


@pytest.fixture
def gitlab_ci_adapter():
    return GitLabCIAdapter(token="glpat-test", api_base="https://gitlab.example/api/v4")


class TestGitLabCIAdapter:
    @pytest.mark.asyncio
    async def test_fetch_ci_results_success_failed_jobs_only(self, gitlab_ci_adapter):
        # MR pipelines response
        pipelines_resp = MagicMock()
        pipelines_resp.json.return_value = [{"id": 101, "sha": "abc"}]
        pipelines_resp.raise_for_status = MagicMock()

        # Pipeline jobs response
        jobs_resp = MagicMock()
        jobs_resp.json.return_value = [
            {"id": 1, "name": "ruff", "status": "failed", "allow_failure": False},
            {"id": 2, "name": "tests", "status": "success", "allow_failure": False},
            {"id": 3, "name": "mypy", "status": "failed", "allow_failure": True},
        ]
        jobs_resp.raise_for_status = MagicMock()

        # Traces
        trace1 = MagicMock()
        trace1.text = "src/main.py:10: F401 unused import"
        trace1.raise_for_status = MagicMock()

        trace3 = MagicMock()
        trace3.text = "src/utils.py:20: error: Incompatible types"
        trace3.raise_for_status = MagicMock()

        with patch.object(gitlab_ci_adapter.client, "get") as mock_get:
            mock_get.side_effect = [pipelines_resp, jobs_resp, trace1, trace3]

            results = await gitlab_ci_adapter.fetch_ci_results(repo="group/proj", pr_number=7)

        assert len(results) == 2
        assert {r.tool_name for r in results} == {"ruff", "mypy"}

        ruff = [r for r in results if r.tool_name == "ruff"][0]
        assert ruff.status == "failure"
        assert "src/main.py" in ruff.files_mentioned

        mypy = [r for r in results if r.tool_name == "mypy"][0]
        assert mypy.status == "warning"  # allow_failure
        assert "src/utils.py" in mypy.files_mentioned

    @pytest.mark.asyncio
    async def test_fetch_ci_results_no_pipelines(self, gitlab_ci_adapter):
        pipelines_resp = MagicMock()
        pipelines_resp.json.return_value = []
        pipelines_resp.raise_for_status = MagicMock()

        with patch.object(gitlab_ci_adapter.client, "get", return_value=pipelines_resp):
            results = await gitlab_ci_adapter.fetch_ci_results(repo="group/proj", pr_number=7)

        assert results == []

    @pytest.mark.asyncio
    async def test_get_check_runs_by_sha(self, gitlab_ci_adapter):
        pipelines_resp = MagicMock()
        pipelines_resp.json.return_value = [{"id": 222}]
        pipelines_resp.raise_for_status = MagicMock()

        jobs_resp = MagicMock()
        jobs_resp.json.return_value = [
            {"id": 9, "name": "lint", "status": "failed", "allow_failure": False},
        ]
        jobs_resp.raise_for_status = MagicMock()

        trace = MagicMock()
        trace.text = "src/app.js:3: error: no-unused-vars"
        trace.raise_for_status = MagicMock()

        with patch.object(gitlab_ci_adapter.client, "get") as mock_get:
            mock_get.side_effect = [pipelines_resp, jobs_resp, trace]
            results = await gitlab_ci_adapter.get_check_runs(repo="group/proj", commit_sha="deadbeef")

        assert len(results) == 1
        assert results[0].tool_name == "lint"
        assert results[0].status == "failure"
        assert "src/app.js" in results[0].files_mentioned

    @pytest.mark.asyncio
    async def test_fetch_ci_results_http_error(self, gitlab_ci_adapter):
        import httpx

        with patch.object(gitlab_ci_adapter.client, "get") as mock_get:
            mock_get.side_effect = httpx.HTTPError("boom")

            with pytest.raises(CIFetchError, match="Error fetching CI results"):
                await gitlab_ci_adapter.fetch_ci_results(repo="group/proj", pr_number=7)

    @pytest.mark.asyncio
    async def test_close(self, gitlab_ci_adapter):
        with patch.object(gitlab_ci_adapter.client, "aclose") as mock_close:
            await gitlab_ci_adapter.close()
            mock_close.assert_called_once()
