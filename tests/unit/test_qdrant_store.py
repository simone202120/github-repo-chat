from datetime import UTC, datetime

import pytest
from llama_index.core.embeddings import MockEmbedding
from qdrant_client import QdrantClient

from github_repo_chat.core.archive import RepoArchive
from github_repo_chat.core.errors import RepoNotIndexedError
from github_repo_chat.core.ingestion import RepoManifest, ingest_repo
from github_repo_chat.core.repo_ref import RepoRef
from github_repo_chat.core.splitting import Splitter
from github_repo_chat.infra.qdrant_store import QdrantStore, collection_name
from github_repo_chat.llm.factory import SparseEncoders
from tests.fakes import hashed_bag_of_words, make_zip

REPO = RepoRef("octo", "demo", "main")
FILES: dict[str, str | bytes] = {
    "README.md": "# Demo\n\nInstall with pip.\n",
    "src/a.py": "def add(a, b):\n    return a + b\n",
}


@pytest.fixture
def store() -> QdrantStore:
    sparse = SparseEncoders(hashed_bag_of_words, hashed_bag_of_words)
    store = QdrantStore(QdrantClient(":memory:"), MockEmbedding(embed_dim=8), sparse)
    store.ensure_registry()
    return store


def _ingest(store: QdrantStore, files: dict[str, str | bytes]):
    splitter = Splitter(code_max_chars=500, code_chunk_lines=40, text_chunk_tokens=128)
    return ingest_repo(
        REPO,
        RepoArchive(make_zip(files)),
        store.index_for(REPO),
        splitter,
        max_files=10,
        max_file_bytes=10_000,
    )


def test_collection_name_is_per_repo() -> None:
    assert collection_name(REPO) == "repo__octo--demo"


def test_manifest_round_trip(store: QdrantStore) -> None:
    manifest = RepoManifest(REPO, {"a.py": "h"}, 3, datetime(2026, 1, 2, tzinfo=UTC))
    store.save_manifest(manifest)
    assert store.get_manifest(REPO) == manifest
    assert store.list_manifests() == [manifest]


def test_get_manifest_unknown_repo(store: QdrantStore) -> None:
    assert store.get_manifest(RepoRef("nobody", "nothing")) is None


def test_ingest_and_retrieve(store: QdrantStore) -> None:
    report = _ingest(store, FILES)
    assert report.manifest.chunk_count == 2
    results = store.retriever(REPO, top_k=2).retrieve("Install with pip")
    assert results
    assert {r.node.metadata["path"] for r in results} <= {"README.md", "src/a.py"}


def test_reingest_deletes_removed_files(store: QdrantStore) -> None:
    _ingest(store, FILES)
    report = _ingest(store, {"README.md": FILES["README.md"]})
    assert report.removed == 1
    assert report.manifest.chunk_count == 1
    assert store.index_for(REPO).count_chunks() == 1


def test_delete_files_before_collection_exists_is_noop(store: QdrantStore) -> None:
    index = store.index_for(REPO)
    index.delete_files(["a.py"])
    assert index.count_chunks() == 0


def test_delete_repo_removes_collection_and_manifest(store: QdrantStore) -> None:
    _ingest(store, FILES)
    store.delete_repo(REPO)
    assert store.get_manifest(REPO) is None
    assert store.list_manifests() == []
    assert store.index_for(REPO).count_chunks() == 0


def test_is_healthy(store: QdrantStore) -> None:
    assert store.is_healthy()


def test_is_unhealthy_when_qdrant_unreachable() -> None:
    sparse = SparseEncoders(hashed_bag_of_words, hashed_bag_of_words)
    client = QdrantClient(url="http://127.0.0.1:1", timeout=1, check_compatibility=False)
    assert not QdrantStore(client, MockEmbedding(embed_dim=8), sparse).is_healthy()


def test_retriever_without_collection_raises_not_indexed(store: QdrantStore) -> None:
    with pytest.raises(RepoNotIndexedError):
        store.retriever(REPO, top_k=3)
