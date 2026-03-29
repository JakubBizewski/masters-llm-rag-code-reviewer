"""GitHub adapter for VCS operations."""
from datetime import datetime
from typing import Optional
from uuid import uuid4

import httpx

from acr_system.domain.entities.entities import DiffHunk, PullRequest, PullRequestDiscussionComment, ReviewComment
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
            headers = await self.auth.get_auth_headers(repo=repo)
            
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
                head_sha=data["head"]["sha"],  # Store HEAD commit SHA
            )
            
            return pr
            
        except httpx.HTTPError as e:
            raise VCSAPIError(f"Error fetching PR from GitHub: {e}") from e
    
    async def get_diff_hunks(self, repo: str, pr_number: int) -> list[DiffHunk]:
        """Fetch diff hunks for a PR."""
        try:
            headers = await self.auth.get_auth_headers(repo=repo)
            
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
            headers = await self.auth.get_auth_headers(repo=repo)
            
            # Fetch PR to get head SHA
            pr = await self.get_pull_request(repo, pr_number)
            if not pr.head_sha:
                raise VCSAPIError("Cannot post comment: PR head SHA not available")
            
            url = f"{self.API_BASE}/repos/{repo}/pulls/{pr_number}/comments"
            
            payload = {
                "body": comment.message,
                "path": comment.file_path.value,
                "commit_id": pr.head_sha,
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
        if not comments:
            return
        
        # Fetch PR once to get head SHA
        pr = await self.get_pull_request(repo, pr_number)
        if not pr.head_sha:
            raise VCSAPIError("Cannot post comments: PR head SHA not available")
        
        # Post all comments with the same commit_id
        headers = await self.auth.get_auth_headers(repo=repo)
        
        for comment in comments:
            try:
                if comment.line_number:
                    # Post as review comment (line-specific)
                    url = f"{self.API_BASE}/repos/{repo}/pulls/{pr_number}/comments"
                    payload = {
                        "body": comment.message,
                        "path": comment.file_path.value,
                        "commit_id": pr.head_sha,
                        "line": comment.line_number,
                        "side": "RIGHT",
                    }
                else:
                    # Post as issue comment (general)
                    url = f"{self.API_BASE}/repos/{repo}/issues/{pr_number}/comments"
                    payload = {
                        "body": f"**{comment.file_path.value}**:\n\n{comment.message}"
                    }
                
                response = await self.client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                
            except httpx.HTTPStatusError as e:
                # If line can't be resolved, fallback to general comment
                if e.response.status_code == 422 and comment.line_number:
                    logger.warning(
                        f"Line {comment.line_number} in {comment.file_path.value} "
                        f"could not be resolved, posting as general comment"
                    )
                    url = f"{self.API_BASE}/repos/{repo}/issues/{pr_number}/comments"
                    payload = {
                        "body": f"**{comment.file_path.value}** (line {comment.line_number}):\n\n{comment.message}"
                    }
                    response = await self.client.post(url, json=payload, headers=headers)
                    response.raise_for_status()
                else:
                    raise VCSAPIError(f"Error posting comment to GitHub: {e}") from e
            except httpx.HTTPError as e:
                raise VCSAPIError(f"Error posting comments to GitHub: {e}") from e
    
    async def get_file_content(
        self,
        repo: str,
        file_path: str,
        ref: str,
    ) -> str:
        """Get file content at a specific ref."""
        try:
            headers = await self.auth.get_auth_headers(repo=repo)
            
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

    async def list_merged_pull_requests(
        self,
        repo: str,
        limit: int = 50,
    ) -> list[int]:
        """List merged pull requests (most recent first)."""
        if limit <= 0:
            return []

        try:
            headers = await self.auth.get_auth_headers(repo=repo)
            results: list[int] = []
            per_page = 100
            page = 1

            while len(results) < limit:
                url = f"{self.API_BASE}/repos/{repo}/pulls"
                params = {
                    "state": "closed",
                    "sort": "updated",
                    "direction": "desc",
                    "per_page": per_page,
                    "page": page,
                }

                response = await self.client.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()
                if not data:
                    break

                for pr in data:
                    if pr.get("merged_at"):
                        results.append(int(pr["number"]))
                        if len(results) >= limit:
                            break

                page += 1

            return results[:limit]

        except httpx.HTTPError as e:
            raise VCSAPIError(f"Error listing merged PRs from GitHub: {e}") from e

    async def get_pull_request_discussion_comments(
        self,
        repo: str,
        pr_number: int,
    ) -> list[PullRequestDiscussionComment]:
        """Fetch PR discussion comments (review comments + issue comments)."""
        try:
            headers = await self.auth.get_auth_headers(repo=repo)
            comments: list[PullRequestDiscussionComment] = []

            # 1) Review comments (inline PR review threads)
            review_page = 1
            while True:
                url = f"{self.API_BASE}/repos/{repo}/pulls/{pr_number}/comments"
                params = {"per_page": 100, "page": review_page}
                resp = await self.client.get(url, headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json()
                if not data:
                    break

                for c in data:
                    created_at = _parse_github_datetime(c.get("created_at"))
                    body = (c.get("body") or "").strip()
                    if not body:
                        continue

                    file_path = c.get("path")
                    line_number = c.get("line") or c.get("original_line")
                    in_reply_to_id = c.get("in_reply_to_id")

                    comments.append(
                        PullRequestDiscussionComment(
                            comment_id=int(c["id"]),
                            author=(c.get("user") or {}).get("login") or "unknown",
                            body=body,
                            created_at=created_at or datetime.utcnow(),
                            file_path=FilePath(file_path) if file_path else None,
                            line_number=int(line_number) if isinstance(line_number, int) else None,
                            in_reply_to_id=int(in_reply_to_id) if isinstance(in_reply_to_id, int) else None,
                            url=c.get("html_url"),
                        )
                    )

                review_page += 1

            # 2) Issue comments (general PR discussion)
            issue_page = 1
            while True:
                url = f"{self.API_BASE}/repos/{repo}/issues/{pr_number}/comments"
                params = {"per_page": 100, "page": issue_page}
                resp = await self.client.get(url, headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json()
                if not data:
                    break

                for c in data:
                    created_at = _parse_github_datetime(c.get("created_at"))
                    body = (c.get("body") or "").strip()
                    if not body:
                        continue

                    comments.append(
                        PullRequestDiscussionComment(
                            comment_id=int(c["id"]),
                            author=(c.get("user") or {}).get("login") or "unknown",
                            body=body,
                            created_at=created_at or datetime.utcnow(),
                            file_path=None,
                            line_number=None,
                            in_reply_to_id=None,
                            url=c.get("html_url"),
                        )
                    )

                issue_page += 1

            # Sort chronologically for nicer thread formatting
            comments.sort(key=lambda x: x.created_at)
            return comments

        except httpx.HTTPError as e:
            raise VCSAPIError(f"Error fetching PR discussion from GitHub: {e}") from e


def _parse_github_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        # GitHub returns ISO 8601 with 'Z'
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None
