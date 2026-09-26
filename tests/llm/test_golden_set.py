"""Golden-set evaluation: real embeddings, real Qdrant and a real LLM through OpenRouter."""

from pathlib import Path

import pytest
import yaml
from qdrant_client import QdrantClient

from github_repo_chat.config import Settings
from github_repo_chat.core.archive import RepoArchive
from github_repo_chat.core.chat import ChatEngine
from github_repo_chat.core.ingestion import ingest_repo
from github_repo_chat.core.repo_ref import RepoRef
from github_repo_chat.core.splitting import Splitter
from github_repo_chat.infra.qdrant_store import QdrantStore
from github_repo_chat.llm.factory import build_embed_model, build_llm, build_sparse_encoders

pytestmark = pytest.mark.llm

HERE = Path(__file__).parent
CASES = yaml.safe_load((HERE / "golden_set.yaml").read_text(encoding="utf-8"))
FIXTURE = HERE.parent / "fixtures" / "tinycalc-main.zip"
REPO = RepoRef("golden", "tinycalc")
MIN_HIT_RATE = 0.85


@pytest.fixture(scope="module")
def engine_and_store():
    settings = Settings()
    if not settings.openrouter_api_key.get_secret_value():
        pytest.skip("OPENROUTER_API_KEY is not set")
    store = QdrantStore(
        QdrantClient(url=settings.qdrant_url),
        build_embed_model(settings),
        build_sparse_encoders(settings),
    )
    store.ensure_registry()
    splitter = Splitter(
        code_max_chars=settings.code_chunk_max_chars,
        code_chunk_lines=settings.code_chunk_lines,
        text_chunk_tokens=settings.text_chunk_tokens,
    )
    ingest_repo(
        REPO,
        RepoArchive(FIXTURE.read_bytes()),
        store.index_for(REPO),
        splitter,
        max_files=settings.max_files,
        max_file_bytes=settings.max_file_bytes,
    )
    engine = ChatEngine(build_llm(settings), top_k=settings.top_k, history_turns=0)
    yield engine, store, settings
    store.delete_repo(REPO)


def test_golden_set(engine_and_store) -> None:
    engine, store, settings = engine_and_store
    hits, retrieval_cases, failures = 0, 0, []
    for case in CASES:
        retriever = store.retriever(REPO, engine.candidates)
        answer = engine.answer(REPO, retriever, case["question"])
        paths = {s.path for s in answer.sources}
        if case["expected_files"]:
            retrieval_cases += 1
            hits += bool(paths & set(case["expected_files"]))
        missing = [f for f in case["key_facts"] if f.lower() not in answer.text.lower()]
        print(f"\n{case['question']}\n  sources: {sorted(paths)}\n  answer: {answer.text[:300]}")
        if missing:
            failures.append(f"{case['question']!r} is missing {missing}")
    hit_rate = hits / retrieval_cases
    print(f"\nhit rate@{settings.top_k}: {hit_rate:.2f}")
    assert hit_rate >= MIN_HIT_RATE
    assert not failures, failures
