"""GitLab CI adapter for fetching CI/CD results.

Implements StaticAnalyzer port by mapping GitLab pipelines/jobs to CIToolResult.

Strategy:
- For a Merge Request: find latest MR pipeline, list jobs
- For each job: fetch trace log and expose it as raw_output

Notes:
- GitLab supports both numeric project IDs and URL-encoded namespace/project path.
- This adapter uses the URL-encoded project path to avoid an extra lookup.
"""

from __future__ import annotations

import re
from typing import List, Optional
from urllib.parse import quote_plus

import httpx

from acr_system.domain.entities.entities import CIToolResult
from acr_system.domain.interfaces.ports import StaticAnalyzer
from acr_system.shared.exceptions.infrastructure_exceptions import CIFetchError
from acr_system.shared.logging.logger import get_logger

logger = get_logger(__name__)


class GitLabCIAdapter(StaticAnalyzer):
    """Adapter for GitLab CI/CD API."""

    def __init__(
        self,
        token: str,
        api_base: str = "https://gitlab.com/api/v4",
        timeout_seconds: float = 30.0,
        max_trace_chars: int = 30_000,
    ):
        if not token:
            raise ValueError("GitLab token must be provided")

        self.api_base = api_base.rstrip("/")
        self.token = token
        self.max_trace_chars = max_trace_chars
        self.client = httpx.AsyncClient(timeout=timeout_seconds)

    def _headers(self) -> dict[str, str]:
        return {
            "PRIVATE-TOKEN": self.token,
            "Accept": "application/json",
        }

    def _project(self, repo: str) -> str:
        # GitLab API accepts URL-encoded path in /projects/:id
        return quote_plus(repo)

    async def fetch_ci_results(self, repo: str, pr_number: int) -> List[CIToolResult]:
        """Fetch CI results for a Merge Request (PR equivalent)."""
        try:
            project = self._project(repo)

            # 1) List MR pipelines (most recent first)
            pipelines_url = f"{self.api_base}/projects/{project}/merge_requests/{pr_number}/pipelines"
            resp = await self.client.get(pipelines_url, headers=self._headers(), params={"per_page": 20})
            resp.raise_for_status()
            pipelines = resp.json() or []
            if not pipelines:
                logger.info(f"No pipelines found for MR !{pr_number} in {repo}")
                return []

            latest = pipelines[0]
            pipeline_id = latest.get("id")
            sha = latest.get("sha")
            if not pipeline_id:
                logger.info(f"Latest pipeline missing id for MR !{pr_number} in {repo}")
                return []

            logger.info(f"Fetching GitLab CI results for MR !{pr_number}, pipeline {pipeline_id}, sha {sha}")
            return await self._get_pipeline_job_results(repo=repo, pipeline_id=int(pipeline_id))

        except httpx.HTTPError as e:
            raise CIFetchError(f"Error fetching CI results from GitLab: {e}") from e
        except Exception as e:
            raise CIFetchError(f"Unexpected error fetching CI results from GitLab: {e}") from e

    async def get_check_runs(self, repo: str, commit_sha: str) -> List[CIToolResult]:
        """Get CI job results for the latest pipeline for a commit SHA."""
        try:
            project = self._project(repo)

            pipelines_url = f"{self.api_base}/projects/{project}/pipelines"
            resp = await self.client.get(
                pipelines_url,
                headers=self._headers(),
                params={
                    "sha": commit_sha,
                    "per_page": 1,
                    "order_by": "id",
                    "sort": "desc",
                },
            )
            resp.raise_for_status()
            pipelines = resp.json() or []
            if not pipelines:
                return []

            pipeline_id = pipelines[0].get("id")
            if not pipeline_id:
                return []

            return await self._get_pipeline_job_results(repo=repo, pipeline_id=int(pipeline_id))

        except httpx.HTTPError as e:
            raise CIFetchError(f"Error fetching GitLab pipelines: {e}") from e
        except Exception as e:
            raise CIFetchError(f"Unexpected error fetching GitLab pipelines: {e}") from e

    async def _get_pipeline_job_results(self, repo: str, pipeline_id: int) -> List[CIToolResult]:
        project = self._project(repo)

        jobs_url = f"{self.api_base}/projects/{project}/pipelines/{pipeline_id}/jobs"
        resp = await self.client.get(jobs_url, headers=self._headers(), params={"per_page": 100})
        resp.raise_for_status()
        jobs = resp.json() or []

        results: list[CIToolResult] = []
        for job in jobs:
            parsed = await self._parse_job(repo=repo, job=job)
            if parsed:
                results.append(parsed)

        return results

    async def _parse_job(self, repo: str, job: dict) -> Optional[CIToolResult]:
        """Parse a GitLab job into CIToolResult.

        Skips jobs that are not finished yet and jobs that succeeded.
        """
        job_id = job.get("id")
        name = job.get("name") or "Unknown"
        status = job.get("status") or "unknown"  # success, failed, canceled, skipped, running, pending
        allow_failure = bool(job.get("allow_failure", False))

        # Skip unfinished
        if status in {"created", "pending", "running"}:
            return None

        # Skip success (no issues)
        if status == "success":
            return None

        if not job_id:
            return None

        trace = await self._fetch_job_trace(repo=repo, job_id=int(job_id))
        files_mentioned = _extract_files_from_trace(trace)

        # Map GitLab status to our status field
        if status == "failed" and allow_failure:
            mapped_status = "warning"
        elif status in {"failed", "canceled"}:
            mapped_status = "failure"
        elif status == "skipped":
            mapped_status = "skipped"
        else:
            mapped_status = "warning"

        conclusion = status

        raw_output = f"Job: {name}\nStatus: {status}\nAllow failure: {allow_failure}\n\nTrace:\n{trace}"

        return CIToolResult(
            tool_name=name,
            status=mapped_status,
            raw_output=raw_output,
            files_mentioned=files_mentioned,
            conclusion=conclusion,
        )

    async def _fetch_job_trace(self, repo: str, job_id: int) -> str:
        project = self._project(repo)

        trace_url = f"{self.api_base}/projects/{project}/jobs/{job_id}/trace"
        resp = await self.client.get(trace_url, headers=self._headers())
        resp.raise_for_status()

        # GitLab returns plain text
        trace = resp.text or ""
        trace = trace.strip()
        if len(trace) > self.max_trace_chars:
            trace = trace[: self.max_trace_chars] + "\n\n[TRUNCATED]"
        return trace

    async def close(self) -> None:
        await self.client.aclose()


_FILE_RE = re.compile(
    r"(?P<path>(?:[A-Za-z0-9_\-./]+/)*[A-Za-z0-9_\-./]+\.[A-Za-z0-9_]+)(?::(?P<line>\d+))?"
)


def _extract_files_from_trace(trace: str) -> set[str]:
    """Best-effort extraction of file paths mentioned in CI logs."""
    files: set[str] = set()
    if not trace:
        return files

    for match in _FILE_RE.finditer(trace):
        path = match.group("path")
        if not path:
            continue

        # Heuristics to reduce noise
        if path.startswith(("http://", "https://")):
            continue
        if "/" not in path and "." not in path:
            continue

        # Exclude common non-repo paths
        if path.startswith(("/usr/", "/opt/", "/builds/", "/tmp/")):
            continue

        files.add(path)

    return files
