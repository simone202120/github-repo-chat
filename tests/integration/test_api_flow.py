from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from github_repo_chat.api.jobs import JobRegistry
from github_repo_chat.api.main import create_app
from github_repo_chat.api.services import Services
from github_repo_chat.config import Settings
from github_repo_chat.core.chat import ChatEngine
from github_repo_chat.infra.qdrant_store import QdrantStore
from github_repo_chat.infra.tracing import Tracer
from github_repo_chat.llm.factory import build_embed_model, build_sparse_encoders
from tests.fakes import ScriptedLLM

pytestmark = pytest.mark.integration

FIXTURE = (Path(__file__).parent.parent / "fixtures" / "tinycalc-main.zip").read_bytes()


def test_index_chat_and_delete_through_the_api() -> None:
    settings = Settings(_env_file=None, langfuse_public_key="")
    store = QdrantStore(
        QdrantClient(url=settings.qdrant_url),
        build_embed_model(settings),
        build_sparse_encoders(settings),
    )
    store.ensure_registry()
    llm = ScriptedLLM(
        responses=["What happens when divide gets zero?", "It raises DivisionByZeroError [1]."]
    )
    services = Services(
        settings,
        store,
        ChatEngine(llm, top_k=3, history_turns=4),
        Tracer(None),
        JobRegistry(),
        lambda repo: FIXTURE,
    )
    with TestClient(create_app(services)) as client:
        assert client.post("/repos", json={"url": "it-fixture/tinycalc-api"}).status_code == 202
        info = client.get("/repos/it-fixture--tinycalc-api").json()
        assert info["status"] == "ready", info
        assert info["file_count"] == 5

        response = client.post(
            "/chat",
            json={"repo": "it-fixture/tinycalc-api", "question": "What happens on divide by zero?"},
        )
        assert response.status_code == 200
        paths = [s["path"] for s in response.json()["sources"]]
        assert "src/tinycalc/calculator.py" in paths

        assert client.delete("/repos/it-fixture--tinycalc-api").status_code == 204
        assert client.get("/repos/it-fixture--tinycalc-api").status_code == 404
