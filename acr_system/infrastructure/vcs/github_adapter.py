"""GitHub adapter for VCS operations."""
from typing import Optional
from uuid import uuid4

import httpx

from acr_system.domain.entities.entities import DiffHunk, PullRequest, ReviewComment
from acr_system.domain.interfaces.ports import VCSRepository
from acr_system.domain.value_objects.value_objects import FilePath
from acr_system.infrastructure.auth.github_jwt import GitHubAppAuth
from acr_system.shared.exceptions.infrastructure_exceptions import VCSAPIError
from acr_system.shared.logging.logger import get_logger

logger = get_logger(__name__)


class GitHubAdapter(VCSRepository):
    """Adapter for GitHub REST API with GitHub App authentication."""
    
    API_BASE = "https://api.github.com"
    
    def __init__(self, auth: GitHubAppAuth):
        """Initialize GitHub adapter.
        
        Args:
            auth: GitHubAppAuth instance for authentication
        """
        self.auth = auth
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def get_pull_request(self, repo: str, pr_number: int) -> PullRequest:
        """Fetch pull request details."""
        try:
            # Get auth headers (with auto-refresh)
            headers = await self.auth.get_auth_headers()
            
            url = f"{self.API_BASE}/repos/{repo}/pulls/{pr_number}"
            response = await self.client.get(url, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            
            pr = PullRequest(
                id=uuid4(),
                pr_number=pr_number,
                repository=repo,
                title=data["title"],
                description=data["body"] or "",
                author=data["user"]["login"],
                source_branch=data["head"]["ref"],
                target_branch=data["base"]["ref"],
            )
            
            return pr
            
        except httpx.HTTPError as e:
            raise VCSAPIError(f"Error fetching PR from GitHub: {e}") from e
    
    async def get_diff_hunks(self, repo: str, pr_number: int) -> list[DiffHunk]:
        """Fetch diff hunks for a PR."""
        try:
            headers = await self.auth.get_auth_headers()
            
            url = f"{self.API_BASE}/repos/{repo}/pulls/{pr_number}/files"
            response = await self.client.get(url, headers=headers)
            response.raise_for_status()
            
            files = response.json()
            hunks = []
            
            for file in files:
                if file.get("patch"):
                    # Parse patch into hunks
                    file_hunks = self._parse_patch(
                        file_path=file["filename"],
                        patch=file["patch"],
                    )
                    hunks.extend(file_hunks)
            
            return hunks
            
        except httpx.HTTPError as e:
            raise VCSAPIError(f"Error fetching diff from GitHub: {e}") from e
    
    def _parse_patch(self, file_path: str, patch: str) -> list[DiffHunk]:
        """Parse unified diff patch into DiffHunk objects."""
        hunks = []
        lines = patch.split('\n')
        
        current_hunk = None
        hunk_lines = []
        
        for line in lines:
            if line.startswith('@@'):
                # Save previous hunk if exists
                if current_hunk and hunk_lines:
                    current_hunk["content"] = '\n'.join(hunk_lines)
                    hunks.append(DiffHunk(**current_hunk))
                    hunk_lines = []
                
                # Parse hunk header: @@ -old_start,old_count +new_start,new_count @@
                parts = line.split('@@')[1].strip().split()
                old_range = parts[0][1:].split(',')  # Remove '-'
                new_range = parts[1][1:].split(',')  # Remove '+'
                
                old_start = int(old_range[0])
                old_count = int(old_range[1]) if len(old_range) > 1 else 1
                new_start = int(new_range[0])
                new_count = int(new_range[1]) if len(new_range) > 1 else 1
                
                current_hunk = {
                    "file_path": FilePath(file_path),
                    "old_start_line": old_start,
                    "old_line_count": old_count,
                    "new_start_line": new_start,
                    "new_line_count": new_count,
                }
            else:
                # Add line to current hunk
                hunk_lines.append(line)
        
        # Save last hunk
        if current_hunk and hunk_lines:
            current_hunk["content"] = '\n'.join(hunk_lines)
            hunks.append(DiffHunk(**current_hunk))
        
        return hunks
    
    async def post_review_comment(
        self,
        repo: str,
        pr_number: int,
        comment: ReviewComment,
    ) -> None:
        """Post a review comment to the PR."""
        try:
            headers = await self.auth.get_auth_headers()
            
            url = f"{self.API_BASE}/repos/{repo}/pulls/{pr_number}/comments"
            
            payload = {
                "body": comment.message,
                "path": comment.file_path.value,
            }
            
            if comment.line_number:
                payload["line"] = comment.line_number
                payload["side"] = "RIGHT"  # Comment on new version
            
            response = await self.client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            
        except httpx.HTTPError as e:
            raise VCSAPIError(f"Error posting comment to GitHub: {e}") from e
    
    async def post_review_comments(
        self,
        repo: str,
        pr_number: int,
        comments: list[ReviewComment],
    ) -> None:
        """Post multiple review comments to the PR."""
        for comment in comments:
            await self.post_review_comment(repo, pr_number, comment)
    
    async def get_file_content(
        self,
        repo: str,
        file_path: str,
        ref: str,
    ) -> str:
        """Get file content at a specific ref."""
        try:
            headers = await self.auth.get_auth_headers()
            
            url = f"{self.API_BASE}/repos/{repo}/contents/{file_path}"
            params = {"ref": ref}
            
            response = await self.client.get(url, params=params, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            
            # Decode base64 content
            import base64
            content = base64.b64decode(data["content"]).decode("utf-8")
            
            return content
            
        except httpx.HTTPError as e:
            raise VCSAPIError(f"Error fetching file from GitHub: {e}") from e
    
    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()
