import pytest
import httpx

from acr_system.domain.entities.entities import ReviewComment
from acr_system.domain.value_objects.value_objects import Severity
from acr_system.domain.value_objects.value_objects import FilePath
from acr_system.infrastructure.vcs.gitlab_adapter import GitLabAdapter
from acr_system.shared.exceptions.infrastructure_exceptions import VCSAPIError


class _Resp:
    def __init__(self, json_data=None, text_data="", status_code=200):
        self._json = json_data
        self.text = text_data
        self.status_code = status_code

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.mark.asyncio
async def test_get_pull_request_maps_basic_fields(monkeypatch):
    adapter = GitLabAdapter(token="x", api_base="https://gitlab.example/api/v4")

    async def fake_get(url, headers=None, params=None):
        assert "/projects/group%2Fproj/merge_requests/12" in url
        return _Resp(
            {
                "title": "T",
                "description": "D",
                "author": {"username": "alice"},
                "source_branch": "feat",
                "target_branch": "main",
                "diff_refs": {"head_sha": "abc"},
            }
        )

    monkeypatch.setattr(adapter.client, "get", fake_get)

    pr = await adapter.get_pull_request("group/proj", 12)
    assert pr.pr_number == 12
    assert pr.repository == "group/proj"
    assert pr.title == "T"
    assert pr.author == "alice"
    assert pr.head_sha == "abc"

    await adapter.close()


@pytest.mark.asyncio
async def test_get_diff_hunks_parses_unified_diff(monkeypatch):
    adapter = GitLabAdapter(token="x", api_base="https://gitlab.example/api/v4")

    diff = """@@ -1,2 +1,3 @@\n line1\n-line2\n+line2_changed\n+line3\n"""

    async def fake_get(url, headers=None, params=None):
        assert url.endswith("/merge_requests/12/changes")
        return _Resp({"changes": [{"new_path": "a.py", "diff": diff}]})

    monkeypatch.setattr(adapter.client, "get", fake_get)

    hunks = await adapter.get_diff_hunks("group/proj", 12)
    assert len(hunks) == 1
    assert hunks[0].file_path == FilePath("a.py")
    assert hunks[0].new_start_line == 1
    assert "line2_changed" in hunks[0].content

    await adapter.close()


@pytest.mark.asyncio
async def test_list_merged_pull_requests_paginates_and_limits(monkeypatch):
    adapter = GitLabAdapter(token="x", api_base="https://gitlab.example/api/v4")

    calls = {"count": 0}

    async def fake_get(url, headers=None, params=None):
        calls["count"] += 1
        if params["page"] == 1:
            return _Resp([{"iid": 3}, {"iid": 2}])
        return _Resp([])

    monkeypatch.setattr(adapter.client, "get", fake_get)

    ids = await adapter.list_merged_pull_requests("group/proj", limit=1)
    assert ids == [3]
    assert calls["count"] == 1

    await adapter.close()


@pytest.mark.asyncio
async def test_get_pull_request_discussion_comments_threads_replies(monkeypatch):
    adapter = GitLabAdapter(token="x", api_base="https://gitlab.example/api/v4")

    discussions = [
        {
            "notes": [
                {
                    "id": 10,
                    "body": "root",
                    "created_at": "2024-01-01T00:00:00Z",
                    "author": {"username": "alice"},
                    "position": {"new_path": "a.py", "new_line": 5},
                    "web_url": "u1",
                },
                {
                    "id": 11,
                    "body": "reply",
                    "created_at": "2024-01-01T00:01:00Z",
                    "author": {"username": "bob"},
                    "web_url": "u2",
                },
            ]
        }
    ]

    async def fake_get(url, headers=None, params=None):
        assert url.endswith("/merge_requests/12/discussions")
        return _Resp(discussions)

    monkeypatch.setattr(adapter.client, "get", fake_get)

    comments = await adapter.get_pull_request_discussion_comments("group/proj", 12)
    assert len(comments) == 2
    assert comments[0].comment_id == 10
    assert comments[0].in_reply_to_id is None
    assert comments[0].file_path == FilePath("a.py")
    assert comments[0].line_number == 5
    assert comments[1].comment_id == 11
    assert comments[1].in_reply_to_id == 10

    await adapter.close()


@pytest.mark.asyncio
async def test_post_review_comments_raises_vcsapierror_on_http_failure(monkeypatch):
    adapter = GitLabAdapter(token="x", api_base="https://gitlab.example/api/v4")

    async def fake_post(url, headers=None, json=None):
        req = httpx.Request("POST", url)
        resp = httpx.Response(500, request=req)
        raise httpx.HTTPStatusError("server error", request=req, response=resp)

    monkeypatch.setattr(adapter.client, "post", fake_post)

    with pytest.raises(VCSAPIError):
        await adapter.post_review_comments(
            "group/proj",
            12,
            [
                ReviewComment(
                    file_path=FilePath("a.py"),
                    line_number=1,
                    severity=Severity(level=Severity.INFO),
                    message="m",
                    suggestion=None,
                )
            ],
        )

    await adapter.close()
