import uuid
from pathlib import Path

import pytest
from qdrant_client import QdrantClient

from github_repo_chat.config import Settings
from github_repo_chat.core.archive import RepoArchive
from github_repo_chat.core.chat import ChatEngine
from github_repo_chat.core.ingestion import ingest_repo
from github_repo_chat.core.repo_ref import RepoRef
from github_repo_chat.core.splitting import Splitter
from github_repo_chat.infra.qdrant_store import QdrantStore
from github_repo_chat.llm.factory import build_embed_model, build_sparse_encoders
from tests.fakes import ScriptedLLM

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).parent.parent / "fixtures" / "tinycalc-main.zip"


@pytest.fixture(scope="module")
def settings() -> Settings:
    return Settings(_env_file=None)


@pytest.fixture(scope="module")
def store(settings: Settings) -> QdrantStore:
    store = QdrantStore(
        QdrantClient(url=settings.qdrant_url),
        build_embed_model(settings),
        build_sparse_encoders(settings),
    )
    store.ensure_registry()
    return store


@pytest.fixture(scope="module")
def repo(store: QdrantStore, settings: Settings):
    repo = RepoRef("fixture", f"tinycalc-{uuid.uuid4().hex[:8]}")
    splitter = Splitter(
        code_max_chars=settings.code_chunk_max_chars,
        code_chunk_lines=settings.code_chunk_lines,
        text_chunk_tokens=settings.text_chunk_tokens,
    )
    archive = RepoArchive(FIXTURE.read_bytes())
    report = ingest_repo(
        repo,
        archive,
        store.index_for(repo),
        splitter,
        max_files=settings.max_files,
        max_file_bytes=settings.max_file_bytes,
    )
    assert report.added == 5
    yield repo
    store.delete_repo(repo)


def _top_paths(store: QdrantStore, repo: RepoRef, question: str, k: int = 3) -> list[str]:
    return [n.node.metadata["path"] for n in store.retriever(repo, k).retrieve(question)]


def test_manifest_lists_indexed_files(store: QdrantStore, repo: RepoRef) -> None:
    manifest = store.get_manifest(repo)
    assert manifest is not None
    assert set(manifest.file_hashes) == {
        "README.md",
        "docs/configuration.md",
        "src/tinycalc/__init__.py",
        "src/tinycalc/calculator.py",
        "src/tinycalc/cli.py",
    }
    assert manifest.chunk_count >= 5


def test_hybrid_retrieval_finds_install_docs(store: QdrantStore, repo: RepoRef) -> None:
    assert "README.md" in _top_paths(store, repo, "How do I install tinycalc?")


def test_hybrid_retrieval_finds_code_by_symbol(store: QdrantStore, repo: RepoRef) -> None:
    assert _top_paths(store, repo, "Where is divide implemented?")[0] == (
        "src/tinycalc/calculator.py"
    )


def test_hybrid_retrieval_finds_config_by_keyword(store: QdrantStore, repo: RepoRef) -> None:
    assert "docs/configuration.md" in _top_paths(store, repo, "TINYCALC_PRECISION")


def test_chat_engine_cites_retrieved_files(store: QdrantStore, repo: RepoRef) -> None:
    engine = ChatEngine(
        ScriptedLLM(responses=["How do I install tinycalc?", "Use pip [1]."]),
        top_k=3,
        history_turns=4,
    )
    answer = engine.answer(repo, store.retriever(repo, 3), "How do I install it?")
    assert answer.text == "Use pip [1]."
    assert answer.sources
    assert answer.sources[0].url.startswith(f"https://github.com/{repo.slug}/blob/HEAD/")


def test_reingest_unchanged_repo_is_noop(
    store: QdrantStore, repo: RepoRef, settings: Settings
) -> None:
    before = store.index_for(repo).count_chunks()
    report = ingest_repo(
        repo,
        RepoArchive(FIXTURE.read_bytes()),
        store.index_for(repo),
        Splitter(code_max_chars=2000, code_chunk_lines=60, text_chunk_tokens=512),
        max_files=settings.max_files,
        max_file_bytes=settings.max_file_bytes,
    )
    assert report.unchanged == 5
    assert report.added == report.changed == report.removed == 0
    assert store.index_for(repo).count_chunks() == before
