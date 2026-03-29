"""GitLab adapter for VCS operations.

Implements VCSRepository port for GitLab Merge Requests.

Notes:
- `repo` is expected as "group/project".
- We post comments as MR notes for simplicity; inline discussions require complex position payloads.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus, quote
from uuid import uuid4

import httpx

from acr_system.domain.entities.entities import (
    DiffHunk,
    PullRequest,
    PullRequestDiscussionComment,
    ReviewComment,
)
from acr_system.domain.interfaces.ports import VCSRepository
from acr_system.domain.value_objects.value_objects import FilePath
from acr_system.shared.exceptions.infrastructure_exceptions import VCSAPIError
from acr_system.shared.logging.logger import get_logger

logger = get_logger(__name__)


class GitLabAdapter(VCSRepository):
    """Adapter for GitLab REST API."""

    def __init__(
        self,
        token: str,
        api_base: str = "https://gitlab.com/api/v4",
        timeout_seconds: float = 30.0,
    ):
        if not token:
            raise ValueError("GitLab token must be provided")

        self.api_base = api_base.rstrip("/")
        self.token = token
        self.client = httpx.AsyncClient(timeout=timeout_seconds)

    def _headers(self) -> dict[str, str]:
        return {
            "PRIVATE-TOKEN": self.token,
            "Accept": "application/json",
        }

    def _project(self, repo: str) -> str:
        # GitLab API accepts URL-encoded path in /projects/:id
        return quote_plus(repo)

    async def get_pull_request(self, repo: str, pr_number: int) -> PullRequest:
        """Fetch Merge Request details."""
        try:
            project = self._project(repo)
            url = f"{self.api_base}/projects/{project}/merge_requests/{pr_number}"
            resp = await self.client.get(url, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()

            author = (data.get("author") or {}).get("username") or (data.get("author") or {}).get("name") or "unknown"
            title = data.get("title") or "(no title)"
            description = data.get("description") or ""
            source_branch = data.get("source_branch") or ""
            target_branch = data.get("target_branch") or ""

            # GitLab provides diff refs with head SHA
            diff_refs = data.get("diff_refs") or {}
            head_sha = diff_refs.get("head_sha") or data.get("sha")

            return PullRequest(
                id=uuid4(),
                pr_number=pr_number,
                repository=repo,
                title=title,
                description=description,
                author=author,
                source_branch=source_branch,
                target_branch=target_branch,
                head_sha=head_sha,
            )

        except httpx.HTTPError as e:
            raise VCSAPIError(f"Error fetching MR from GitLab: {e}") from e

    async def get_diff_hunks(self, repo: str, pr_number: int) -> list[DiffHunk]:
        """Fetch diff hunks for a Merge Request."""
        try:
            project = self._project(repo)
            url = f"{self.api_base}/projects/{project}/merge_requests/{pr_number}/changes"
            resp = await self.client.get(url, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()

            changes = data.get("changes", []) or []
            hunks: list[DiffHunk] = []

            for change in changes:
                diff = change.get("diff")
                # Skip if no diff (binary files etc.)
                if not diff:
                    continue

                file_path = change.get("new_path") or change.get("old_path") or "unknown"
                hunks.extend(self._parse_patch(file_path=file_path, patch=diff))

            return hunks

        except httpx.HTTPError as e:
            raise VCSAPIError(f"Error fetching MR diff from GitLab: {e}") from e

    def _parse_patch(self, file_path: str, patch: str) -> list[DiffHunk]:
        """Parse unified diff patch into DiffHunk objects."""
        hunks: list[DiffHunk] = []
        lines = patch.split("\n")

        current_hunk: Optional[dict] = None
        hunk_lines: list[str] = []

        for line in lines:
            if line.startswith("@@"):
                if current_hunk and hunk_lines:
                    current_hunk["content"] = "\n".join(hunk_lines)
                    hunks.append(DiffHunk(**current_hunk))
                    hunk_lines = []

                # Parse header: @@ -old_start,old_count +new_start,new_count @@
                parts = line.split("@@")[1].strip().split()
                if len(parts) < 2:
                    continue

                old_range = parts[0][1:].split(",")
                new_range = parts[1][1:].split(",")

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
                hunk_lines.append(line)

        if current_hunk and hunk_lines:
            current_hunk["content"] = "\n".join(hunk_lines)
            hunks.append(DiffHunk(**current_hunk))

        return hunks

    async def post_review_comment(self, repo: str, pr_number: int, comment: ReviewComment) -> None:
        """Post a review comment to MR as a note.

        GitLab inline review comments require a `position` payload; for MVP we post notes.
        """
        await self.post_review_comments(repo=repo, pr_number=pr_number, comments=[comment])

    async def post_review_comments(self, repo: str, pr_number: int, comments: list[ReviewComment]) -> None:
        if not comments:
            return

        try:
            project = self._project(repo)
            url = f"{self.api_base}/projects/{project}/merge_requests/{pr_number}/notes"

            for c in comments:
                location = ""
                if c.line_number:
                    location = f" ({c.file_path.value}:{c.line_number})"
                elif c.file_path:
                    location = f" ({c.file_path.value})"

                body = f"[{c.severity.level.upper()}]{location}\n\n{c.message}"

                payload = {"body": body}
                resp = await self.client.post(url, headers=self._headers(), json=payload)
                resp.raise_for_status()

        except httpx.HTTPError as e:
            raise VCSAPIError(f"Error posting comment to GitLab: {e}") from e

    async def get_file_content(self, repo: str, file_path: str, ref: str) -> str:
        """Get raw file content at a ref."""
        try:
            project = self._project(repo)
            # file_path is part of URL path, must be URL-encoded (slash-safe)
            encoded_path = quote(file_path, safe="")
            url = f"{self.api_base}/projects/{project}/repository/files/{encoded_path}/raw"
            resp = await self.client.get(url, headers=self._headers(), params={"ref": ref})
            resp.raise_for_status()
            return resp.text

        except httpx.HTTPError as e:
            raise VCSAPIError(f"Error fetching file from GitLab: {e}") from e

    async def list_merged_pull_requests(self, repo: str, limit: int = 50) -> list[int]:
        """List merged merge requests (most recent first)."""
        if limit <= 0:
            return []

        try:
            project = self._project(repo)
            url = f"{self.api_base}/projects/{project}/merge_requests"

            results: list[int] = []
            page = 1
            per_page = 100

            while len(results) < limit:
                resp = await self.client.get(
                    url,
                    headers=self._headers(),
                    params={
                        "state": "merged",
                        "order_by": "updated_at",
                        "sort": "desc",
                        "per_page": per_page,
                        "page": page,
                    },
                )
                resp.raise_for_status()
                data = resp.json() or []
                if not data:
                    break

                for mr in data:
                    iid = mr.get("iid")
                    if iid is not None:
                        results.append(int(iid))
                        if len(results) >= limit:
                            break

                page += 1

            return results[:limit]

        except httpx.HTTPError as e:
            raise VCSAPIError(f"Error listing merged MRs from GitLab: {e}") from e

    async def get_pull_request_discussion_comments(
        self,
        repo: str,
        pr_number: int,
    ) -> list[PullRequestDiscussionComment]:
        """Fetch MR discussions (threads) with replies."""
        try:
            project = self._project(repo)
            url = f"{self.api_base}/projects/{project}/merge_requests/{pr_number}/discussions"

            resp = await self.client.get(url, headers=self._headers(), params={"per_page": 100})
            resp.raise_for_status()
            discussions = resp.json() or []

            comments: list[PullRequestDiscussionComment] = []

            for d in discussions:
                notes = d.get("notes", []) or []
                if not notes:
                    continue

                root_id: Optional[int] = None
                for idx, n in enumerate(notes):
                    note_id = n.get("id")
                    body = (n.get("body") or "").strip()
                    if not note_id or not body:
                        continue

                    if idx == 0:
                        root_id = int(note_id)

                    author = (n.get("author") or {}).get("username") or (n.get("author") or {}).get("name") or "unknown"
                    created_at = _parse_gitlab_datetime(n.get("created_at")) or datetime.utcnow()

                    file_path = None
                    line_number = None
                    position = n.get("position") or {}
                    if position:
                        file_path = position.get("new_path") or position.get("old_path")
                        line_number = position.get("new_line") or position.get("old_line")

                    web_url = n.get("web_url")

                    comments.append(
                        PullRequestDiscussionComment(
                            comment_id=int(note_id),
                            author=author,
                            body=body,
                            created_at=created_at,
                            file_path=FilePath(file_path) if file_path else None,
                            line_number=int(line_number) if isinstance(line_number, int) else None,
                            in_reply_to_id=None if idx == 0 else root_id,
                            url=web_url,
                        )
                    )

            comments.sort(key=lambda x: x.created_at)
            return comments

        except httpx.HTTPError as e:
            raise VCSAPIError(f"Error fetching MR discussions from GitLab: {e}") from e

    async def close(self) -> None:
        await self.client.aclose()


def _parse_gitlab_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None
