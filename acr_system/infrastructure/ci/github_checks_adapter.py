"""GitHub Checks adapter for fetching CI/CD results."""
from typing import Dict, List, Optional

import httpx

from acr_system.domain.entities.entities import CIToolResult
from acr_system.domain.interfaces.ports import StaticAnalyzer
from acr_system.shared.exceptions.infrastructure_exceptions import CIFetchError
from acr_system.shared.logging.logger import get_logger

logger = get_logger(__name__)


class GitHubChecksAdapter(StaticAnalyzer):
    """Adapter for GitHub Checks API to fetch CI/CD results."""
    
    API_BASE = "https://api.github.com"
    
    def __init__(self, token: str):
        """Initialize GitHub Checks adapter.
        
        Args:
            token: GitHub API token with repo access
        """
        self.token = token
        self.client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )
    
    async def fetch_ci_results(
        self,
        repo: str,
        pr_number: int,
    ) -> List[CIToolResult]:
        """Fetch CI results for a pull request.
        
        Args:
            repo: Repository in format "owner/repo"
            pr_number: Pull request number
            
        Returns:
            List of CI tool results
            
        Raises:
            CIFetchError: If fetching CI results fails
        """
        try:
            # First, get the PR to find the head commit SHA
            pr_url = f"{self.API_BASE}/repos/{repo}/pulls/{pr_number}"
            pr_response = await self.client.get(pr_url)
            pr_response.raise_for_status()
            pr_data = pr_response.json()
            
            head_sha = pr_data["head"]["sha"]
            logger.info(f"Fetching CI results for PR #{pr_number}, commit {head_sha}")
            
            # Get check runs for this commit
            return await self.get_check_runs(repo=repo, commit_sha=head_sha)
            
        except httpx.HTTPError as e:
            raise CIFetchError(f"Error fetching CI results from GitHub: {e}") from e
        except Exception as e:
            raise CIFetchError(f"Unexpected error fetching CI results: {e}") from e
    
    async def get_check_runs(
        self,
        repo: str,
        commit_sha: str,
    ) -> List[CIToolResult]:
        """Get check runs for a specific commit.
        
        Args:
            repo: Repository in format "owner/repo"
            commit_sha: Commit SHA
            
        Returns:
            List of CI tool results
            
        Raises:
            CIFetchError: If fetching check runs fails
        """
        try:
            url = f"{self.API_BASE}/repos/{repo}/commits/{commit_sha}/check-runs"
            response = await self.client.get(url)
            response.raise_for_status()
            
            data = response.json()
            check_runs = data.get("check_runs", [])
            
            logger.info(f"Found {len(check_runs)} check runs for commit {commit_sha}")
            
            results = []
            for check_run in check_runs:
                result = await self._parse_check_run(check_run, repo, commit_sha)
                if result:
                    results.append(result)
            
            return results
            
        except httpx.HTTPError as e:
            raise CIFetchError(f"Error fetching check runs from GitHub: {e}") from e
        except Exception as e:
            raise CIFetchError(f"Unexpected error fetching check runs: {e}") from e
    
    async def _parse_check_run(
        self,
        check_run: dict,
        repo: str,
        commit_sha: str,
    ) -> Optional[CIToolResult]:
        """Parse a single check run into CIToolResult.
        
        Args:
            check_run: Check run data from GitHub API
            repo: Repository name
            commit_sha: Commit SHA
            
        Returns:
            CIToolResult or None if check run should be ignored
        """
        tool_name = check_run.get("name", "Unknown")
        status = check_run.get("status", "unknown")  # queued, in_progress, completed
        conclusion = check_run.get("conclusion", "neutral")  # success, failure, neutral, etc.
        
        # Skip if not completed
        if status != "completed":
            logger.debug(f"Skipping check run {tool_name} - status: {status}")
            return None
        
        # Skip if successful (no issues to report)
        if conclusion == "success":
            logger.debug(f"Check run {tool_name} passed successfully")
            return None
        
        # Get output text
        output = check_run.get("output", {})
        title = output.get("title", "")
        summary = output.get("summary", "")
        text = output.get("text", "")
        
        # Combine output into raw_output
        raw_output = f"Title: {title}\n\nSummary:\n{summary}\n\nDetails:\n{text}"
        
        # Get annotations (specific line-level issues)
        annotations = await self._fetch_annotations(check_run.get("id"), repo)
        if annotations:
            raw_output += "\n\nAnnotations:\n"
            for annotation in annotations:
                path = annotation.get("path", "unknown")
                start_line = annotation.get("start_line", 0)
                level = annotation.get("annotation_level", "notice")
                message = annotation.get("message", "")
                raw_output += f"[{level}] {path}:{start_line} - {message}\n"
        
        # Extract files mentioned (from annotations)
        files_mentioned = set()
        if annotations:
            for annotation in annotations:
                if "path" in annotation:
                    files_mentioned.add(annotation["path"])
        
        # Map GitHub conclusion to our status
        status_map = {
            "success": "success",
            "failure": "failure",
            "neutral": "warning",
            "cancelled": "skipped",
            "skipped": "skipped",
            "timed_out": "failure",
            "action_required": "warning",
        }
        
        return CIToolResult(
            tool_name=tool_name,
            status=status_map.get(conclusion, "warning"),
            raw_output=raw_output,
            files_mentioned=files_mentioned,
            conclusion=conclusion,
        )
    
    async def _fetch_annotations(
        self,
        check_run_id: Optional[int],
        repo: str,
    ) -> List[Dict]:
        """Fetch annotations (line-level issues) for a check run.
        
        Args:
            check_run_id: Check run ID
            repo: Repository name
            
        Returns:
            List of annotations
        """
        if not check_run_id:
            return []
        
        try:
            url = f"{self.API_BASE}/repos/{repo}/check-runs/{check_run_id}/annotations"
            response = await self.client.get(url)
            
            # Annotations endpoint might not be available for all check runs
            if response.status_code == 404:
                return []
            
            response.raise_for_status()
            annotations = response.json()
            
            logger.debug(f"Fetched {len(annotations)} annotations for check run {check_run_id}")
            return annotations
            
        except Exception as e:
            logger.warning(f"Could not fetch annotations for check run {check_run_id}: {e}")
            return []
    
    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()
