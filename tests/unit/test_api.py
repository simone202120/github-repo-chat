import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from llama_index.core.embeddings import MockEmbedding
from qdrant_client import QdrantClient

from github_repo_chat.api.jobs import JobRegistry
from github_repo_chat.api.main import create_app
from github_repo_chat.api.services import Services
from github_repo_chat.config import Settings
from github_repo_chat.core.chat import ChatEngine
from github_repo_chat.core.errors import RepoNotFoundError
from github_repo_chat.core.repo_ref import RepoRef
from github_repo_chat.infra.qdrant_store import QdrantStore
from github_repo_chat.infra.tracing import Tracer
from github_repo_chat.llm.factory import SparseEncoders
from tests.fakes import ScriptedLLM, hashed_bag_of_words, make_zip

FIXTURE = (Path(__file__).parent.parent / "fixtures" / "tinycalc-main.zip").read_bytes()


def _fetch(repo: RepoRef) -> bytes:
    if repo.name == "missing":
        raise RepoNotFoundError(f"Repository or branch not found: {repo.slug}")
    return FIXTURE


@pytest.fixture
def llm() -> ScriptedLLM:
    return ScriptedLLM()


@pytest.fixture
def services(llm: ScriptedLLM) -> Services:
    sparse = SparseEncoders(hashed_bag_of_words, hashed_bag_of_words)
    store = QdrantStore(QdrantClient(":memory:"), MockEmbedding(embed_dim=8), sparse)
    store.ensure_registry()
    engine = ChatEngine(llm, top_k=3, history_turns=4)
    settings = Settings(_env_file=None, langfuse_public_key="")
    return Services(settings, store, engine, Tracer(None), JobRegistry(), _fetch)


@pytest.fixture
def client(services: Services) -> Iterator[TestClient]:
    with TestClient(create_app(services)) as client:
        yield client


def _index(client: TestClient, url: str = "https://github.com/octo/tinycalc") -> dict:
    response = client.post("/repos", json={"url": url})
    assert response.status_code == 202
    return response.json()


def test_health_reports_qdrant_and_tracing(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "qdrant": True, "tracing": False}


def test_health_degraded_when_qdrant_down(client: TestClient, services: Services, monkeypatch):
    monkeypatch.setattr(services.store, "is_healthy", lambda: False)
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


def test_add_repo_returns_job_and_indexes_in_background(client: TestClient) -> None:
    job = _index(client)
    assert job["id"] == "octo--tinycalc"
    assert job["status"] == "queued"

    info = client.get("/repos/octo--tinycalc").json()
    assert info["status"] == "ready"
    assert info["stage"] == "done"
    assert info["file_count"] == 5
    assert info["chunk_count"] > 5
    assert info["indexed_at"] is not None


def test_add_repo_with_branch(client: TestClient) -> None:
    response = client.post("/repos", json={"url": "octo/tinycalc", "branch": "dev"})
    assert response.json()["branch"] == "dev"
    assert client.get("/repos/octo--tinycalc").json()["branch"] == "dev"


@pytest.mark.parametrize(
    "body",
    [{"url": "not a repo"}, {"url": "https://gitlab.com/a/b"}, {"url": "a/b", "branch": "../x"}],
)
def test_add_repo_rejects_invalid_input(client: TestClient, body: dict) -> None:
    assert client.post("/repos", json=body).status_code == 422


def test_add_repo_rejects_oversized_url(client: TestClient) -> None:
    assert client.post("/repos", json={"url": "a/" + "b" * 400}).status_code == 422


def test_add_repo_conflict_while_indexing(client: TestClient, services: Services) -> None:
    services.jobs.start(RepoRef("octo", "tinycalc"))
    assert client.post("/repos", json={"url": "octo/tinycalc"}).status_code == 409


def test_failed_ingestion_is_reported(client: TestClient) -> None:
    _index(client, "octo/missing")
    info = client.get("/repos/octo--missing").json()
    assert info["status"] == "failed"
    assert "not found" in info["error"]


def test_list_repos_merges_indexed_and_failed(client: TestClient) -> None:
    _index(client)
    _index(client, "octo/missing")
    repos = client.get("/repos").json()
    assert [(r["repo"], r["status"]) for r in repos] == [
        ("octo/missing", "failed"),
        ("octo/tinycalc", "ready"),
    ]


def test_list_repos_empty(client: TestClient) -> None:
    assert client.get("/repos").json() == []


def test_get_unknown_repo_returns_404(client: TestClient) -> None:
    assert client.get("/repos/nobody--nothing").status_code == 404


def test_get_repo_with_invalid_id_returns_422(client: TestClient) -> None:
    assert client.get("/repos/nodash").status_code == 422


def test_delete_repo(client: TestClient) -> None:
    _index(client)
    assert client.delete("/repos/octo--tinycalc").status_code == 204
    assert client.get("/repos/octo--tinycalc").status_code == 404
    assert client.get("/repos").json() == []


def test_delete_repo_while_indexing_conflicts(client: TestClient, services: Services) -> None:
    services.jobs.start(RepoRef("octo", "busy"))
    assert client.delete("/repos/octo--busy").status_code == 409


def test_delete_unknown_repo_returns_404(client: TestClient) -> None:
    assert client.delete("/repos/nobody--nothing").status_code == 404


def test_chat_answers_with_sources(client: TestClient, llm: ScriptedLLM) -> None:
    _index(client)
    llm.responses.append("Install it with pip [1].")
    response = client.post(
        "/chat", json={"repo": "octo/tinycalc", "question": "How do I install tinycalc?"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Install it with pip [1]."
    assert body["standalone_question"] == "How do I install tinycalc?"
    assert body["usage"] == {"prompt_tokens": 0, "completion_tokens": 0, "cost_usd": None}
    assert body["latency_ms"] >= 0
    assert body["trace_url"] is None
    assert 1 <= len(body["sources"]) <= 3
    source = body["sources"][0]
    assert source["number"] == 1
    assert source["url"].startswith("https://github.com/octo/tinycalc/blob/HEAD/")


def test_chat_accepts_repo_id_and_history(client: TestClient, llm: ScriptedLLM) -> None:
    _index(client)
    llm.responses.extend(["How does divide handle zero?", "It raises [1]."])
    history = [
        {"role": "user", "content": "What does divide do?"},
        {"role": "assistant", "content": "It divides."},
    ]
    response = client.post(
        "/chat",
        json={"repo": "octo--tinycalc", "question": "And with zero?", "history": history},
    )
    assert response.status_code == 200
    assert response.json()["standalone_question"] == "How does divide handle zero?"


def test_chat_unknown_repo_returns_404(client: TestClient) -> None:
    response = client.post("/chat", json={"repo": "octo/nothing", "question": "hi"})
    assert response.status_code == 404


def test_chat_repository_without_content_returns_404(
    client: TestClient, services: Services, llm: ScriptedLLM, monkeypatch
) -> None:
    monkeypatch.setattr(services, "fetch_archive", lambda repo: make_zip({"image.png": b"\x00"}))
    _index(client, "octo/empty")
    response = client.post("/chat", json={"repo": "octo/empty", "question": "What is it?"})
    assert response.status_code == 404
    assert "no indexed content" in response.json()["detail"]
    assert llm.prompts == []


@pytest.mark.parametrize(
    "body",
    [
        {"repo": "octo/tinycalc", "question": ""},
        {"repo": "octo/tinycalc", "question": "x" * 2001},
        {"repo": "octo/tinycalc", "question": "q", "history": [{"role": "system", "content": "x"}]},
        {
            "repo": "octo/tinycalc",
            "question": "q",
            "history": [{"role": "user", "content": "x"}] * 21,
        },
    ],
)
def test_chat_validates_input(client: TestClient, body: dict) -> None:
    assert client.post("/chat", json=body).status_code == 422


def test_reindex_is_rejected_while_delete_is_in_flight(
    client: TestClient, services: Services, monkeypatch
) -> None:
    _index(client)
    started, release = threading.Event(), threading.Event()
    real_delete = services.store.delete_repo

    def slow_delete(repo: RepoRef) -> None:
        started.set()
        assert release.wait(timeout=5)
        real_delete(repo)

    monkeypatch.setattr(services.store, "delete_repo", slow_delete)
    result: dict[str, int] = {}
    thread = threading.Thread(
        target=lambda: result.update(code=client.delete("/repos/octo--tinycalc").status_code)
    )
    thread.start()
    assert started.wait(timeout=5)

    assert client.get("/repos/octo--tinycalc").json()["status"] == "deleting"
    assert client.post("/repos", json={"url": "octo/tinycalc"}).status_code == 409

    release.set()
    thread.join(timeout=5)
    assert result["code"] == 204
    assert client.get("/repos/octo--tinycalc").status_code == 404
    assert client.post("/repos", json={"url": "octo/tinycalc"}).status_code == 202


def test_delete_failure_releases_the_repository(
    client: TestClient, services: Services, monkeypatch
) -> None:
    _index(client)

    def broken(repo: RepoRef) -> None:
        raise RuntimeError("qdrant down")

    monkeypatch.setattr(services.store, "delete_repo", broken)
    with pytest.raises(RuntimeError):
        client.delete("/repos/octo--tinycalc")
    assert services.jobs.get("octo--tinycalc") is None


def test_list_repos_reports_indexed_branch_after_job_is_forgotten(
    client: TestClient, services: Services
) -> None:
    client.post("/repos", json={"url": "octo/tinycalc", "branch": "dev"})
    services.jobs.discard("octo--tinycalc")
    assert [(r["repo"], r["branch"]) for r in client.get("/repos").json()] == [
        ("octo/tinycalc", "dev")
    ]
    assert client.get("/repos/octo--tinycalc").json()["branch"] == "dev"


def test_job_update_after_discard_is_ignored(services: Services) -> None:
    services.jobs.start(RepoRef("octo", "gone"))
    services.jobs.discard("octo--gone")
    services.jobs.update("octo--gone", status="failed")
    assert services.jobs.get("octo--gone") is None
