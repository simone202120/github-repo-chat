"""Thin HTTP client for the API, used by the Streamlit UI."""

from typing import Any

import httpx

_CHAT_TIMEOUT_S = 120.0


class ApiError(Exception):
    """The API is unreachable (`status` is None) or answered with an error status."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class ApiClient:
    def __init__(self, base_url: str, transport: httpx.BaseTransport | None = None) -> None:
        self.base_url = base_url
        self._http = httpx.Client(base_url=base_url, timeout=10.0, transport=transport)

    def add_repo(self, url: str, branch: str | None) -> dict[str, Any]:
        job: dict[str, Any] = self._request("POST", "/repos", json={"url": url, "branch": branch})
        return job

    def repo(self, repo_id: str) -> dict[str, Any]:
        info: dict[str, Any] = self._request("GET", f"/repos/{repo_id}")
        return info

    def repos(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = self._request("GET", "/repos")
        return result

    def delete_repo(self, repo_id: str) -> None:
        self._request("DELETE", f"/repos/{repo_id}")

    def chat(self, repo_id: str, question: str, history: list[dict[str, str]]) -> dict[str, Any]:
        body = {"repo": repo_id, "question": question, "history": history}
        reply: dict[str, Any] = self._request("POST", "/chat", json=body, timeout=_CHAT_TIMEOUT_S)
        return reply

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise ApiError(f"API unreachable: {exc}") from exc
        if response.is_error:
            raise ApiError(_detail(response), response.status_code)
        return response.json() if response.content else None


def _detail(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail", response.text)
    except ValueError:
        detail = response.text
    if isinstance(detail, list):
        detail = "; ".join(str(item.get("msg", item)) for item in detail)
    return str(detail)
