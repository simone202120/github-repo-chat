import json

import httpx
import pytest

from github_repo_chat.ui.client import ApiClient, ApiError


def _client(handler) -> ApiClient:
    return ApiClient("http://api", transport=httpx.MockTransport(handler))


def test_add_repo_posts_url_and_branch() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(202, json={"id": "a--b"})

    assert _client(handler).add_repo("a/b", None) == {"id": "a--b"}
    assert seen == [{"url": "a/b", "branch": None}]


def test_chat_sends_history() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/chat"
        body = json.loads(request.content)
        return httpx.Response(200, json={"answer": body["question"], "sources": []})

    reply = _client(handler).chat("a--b", "q?", [{"role": "user", "content": "hi"}])
    assert reply["answer"] == "q?"


def test_delete_repo_handles_empty_body() -> None:
    assert _client(lambda r: httpx.Response(204)).delete_repo("a--b") is None


def test_repos_lists() -> None:
    assert _client(lambda r: httpx.Response(200, json=[{"id": "x"}])).repos() == [{"id": "x"}]


def test_error_detail_is_surfaced() -> None:
    with pytest.raises(ApiError, match=r"^Repository a/b is not indexed$"):
        _client(
            lambda r: httpx.Response(404, json={"detail": "Repository a/b is not indexed"})
        ).repo("a--b")


def test_validation_errors_are_joined() -> None:
    detail = [{"msg": "too long"}, {"msg": "bad role"}]
    with pytest.raises(ApiError, match=r"^too long; bad role$"):
        _client(lambda r: httpx.Response(422, json={"detail": detail})).repos()


def test_non_json_error_body() -> None:
    with pytest.raises(ApiError, match=r"^Bad Gateway$"):
        _client(lambda r: httpx.Response(502, text="Bad Gateway")).repos()


def test_unreachable_api() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ApiError, match="unreachable"):
        _client(handler).repos()
