from pathlib import Path
from typing import Any, ClassVar

import pytest
from streamlit.testing.v1 import AppTest

from github_repo_chat.config import get_settings
from github_repo_chat.ui import client as client_module

APP = str(Path(client_module.__file__).parent / "app.py")
READY = {
    "id": "a--b",
    "repo": "a/b",
    "branch": None,
    "status": "ready",
    "stage": "done",
    "progress_done": 4,
    "progress_total": 4,
    "error": None,
    "file_count": 3,
    "chunk_count": 9,
}
REPLY = {
    "answer": "Use pip [1].",
    "sources": [
        {
            "number": 1,
            "path": "README.md",
            "symbol": "Install",
            "start_line": 3,
            "url": "https://github.com/a/b/blob/HEAD/README.md#L3",
            "score": 0.8,
        }
    ],
    "standalone_question": "How to install?",
    "usage": {"prompt_tokens": 1200, "completion_tokens": 34, "cost_usd": 0.00042},
    "latency_ms": 1530,
    "trace_url": "https://langfuse.test/trace/1",
}


class FakeApi:
    repos_list: ClassVar[list[dict[str, Any]]] = []
    calls: ClassVar[list[tuple]] = []
    error: client_module.ApiError | None = None

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url

    def repos(self):
        if FakeApi.error:
            raise FakeApi.error
        return FakeApi.repos_list

    def add_repo(self, url, branch):
        FakeApi.calls.append(("add", url, branch))
        FakeApi.repos_list = [READY]
        return {"id": "a--b", "repo": url, "status": "queued"}

    def repo(self, repo_id):
        return READY

    def delete_repo(self, repo_id):
        FakeApi.calls.append(("delete", repo_id))
        FakeApi.repos_list = []

    def chat(self, repo_id, question, history):
        FakeApi.calls.append(("chat", repo_id, question, history))
        return REPLY


@pytest.fixture(autouse=True)
def _fake_api(monkeypatch):
    get_settings.cache_clear()
    FakeApi.repos_list, FakeApi.calls, FakeApi.error = [], [], None
    monkeypatch.setattr(client_module, "ApiClient", FakeApi)


def _run() -> AppTest:
    app = AppTest.from_file(APP, default_timeout=10).run()
    assert not app.exception
    return app


def _button(app: AppTest, key: str):
    return next(b for b in app.button if b.key == key)


def test_empty_state_offers_three_example_repositories() -> None:
    app = _run()
    keys = [b.key for b in app.button if b.key.startswith("example:")]
    assert keys == [
        "example:fastapi/fastapi",
        "example:pallets/flask",
        "example:langchain-ai/langgraph",
    ]


def test_example_click_indexes_the_repository() -> None:
    app = _run()
    _button(app, "example:pallets/flask").click().run()
    assert not app.exception
    assert FakeApi.calls[0] == ("add", "pallets/flask", None)


def test_chat_empty_state_offers_example_questions() -> None:
    FakeApi.repos_list = [READY]
    app = _run()
    assert [b.key for b in app.button if b.key.startswith("question:")] == [
        "question:What is this project for?",
        "question:How do I install and run it?",
        "question:Where is the main entry point implemented?",
    ]


def test_chat_shows_answer_sources_and_metrics() -> None:
    FakeApi.repos_list = [READY]
    app = _run()
    app.chat_input[0].set_value("How to install?").run()
    assert not app.exception
    assert FakeApi.calls == [("chat", "a--b", "How to install?", [])]
    markdown = " ".join(m.value for m in app.markdown)
    assert "Use pip [1]." in markdown
    assert "`README.md`:3" in markdown
    assert "langfuse.test/trace/1" in markdown
    metrics = {m.label: m.value for m in app.metric}
    assert metrics == {"Tokens": "1,234", "Cost": "$0.00042", "Latency": "1.5 s"}


def test_second_question_sends_history() -> None:
    FakeApi.repos_list = [READY]
    app = _run()
    app.chat_input[0].set_value("First?").run()
    app.chat_input[0].set_value("Second?").run()
    assert FakeApi.calls[-1][3] == [
        {"role": "user", "content": "First?"},
        {"role": "assistant", "content": "Use pip [1]."},
    ]


def test_delete_button_removes_repository() -> None:
    FakeApi.repos_list = [READY]
    app = _run()
    _button(app, "delete:a--b").click().run()
    assert ("delete", "a--b") in FakeApi.calls


def test_unreachable_backend_shows_friendly_error() -> None:
    FakeApi.error = client_module.ApiError("API unreachable: refused")
    app = _run()
    assert "docker compose up" in app.error[0].value


def test_blank_url_submit_warns() -> None:
    app = _run()
    app.sidebar.button[0].click().run()
    assert "Enter a GitHub URL" in app.sidebar.warning[0].value
    assert FakeApi.calls == []
