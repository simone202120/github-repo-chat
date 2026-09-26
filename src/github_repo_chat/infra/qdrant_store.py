"""Qdrant adapter: one hybrid (dense + BM25) collection per repository plus a manifest registry."""

import logging
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from llama_index.core import VectorStoreIndex
from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.embeddings import BaseEmbedding
from llama_index.core.schema import BaseNode
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient, models

from github_repo_chat.core.errors import RepoNotIndexedError
from github_repo_chat.core.ingestion import RepoManifest
from github_repo_chat.core.repo_ref import RepoRef, parse_repo
from github_repo_chat.llm.factory import SparseEncoders

logger = logging.getLogger(__name__)

REGISTRY_COLLECTION = "github_repo_chat_registry"
_COLLECTION_PREFIX = "repo__"
_DOC_ID_KEY = "doc_id"
# Hybrid retrieval asks the sparse (BM25) side for a wider pool before score fusion.
_SPARSE_POOL_FACTOR = 2


def collection_name(repo: RepoRef) -> str:
    return f"{_COLLECTION_PREFIX}{repo.id}"


def _point_id(repo: RepoRef) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, repo.slug))


class QdrantStore:
    """Entry point for everything persisted in Qdrant; safe to share between threads."""

    def __init__(
        self, client: QdrantClient, embed_model: BaseEmbedding, sparse: SparseEncoders
    ) -> None:
        self._client = client
        self._embed_model = embed_model
        self._sparse = sparse

    def ensure_registry(self) -> None:
        if not self._client.collection_exists(REGISTRY_COLLECTION):
            # Payload-only points: the registry needs no vectors.
            self._client.create_collection(REGISTRY_COLLECTION, vectors_config={})

    def is_healthy(self) -> bool:
        try:
            self._client.get_collections()
        except Exception:
            logger.exception("Qdrant health check failed")
            return False
        return True

    def index_for(self, repo: RepoRef) -> "QdrantRepoIndex":
        return QdrantRepoIndex(self, self._client, repo, self._vector_index(repo))

    def retriever(self, repo: RepoRef, top_k: int) -> BaseRetriever:
        if not self._client.collection_exists(collection_name(repo)):
            raise RepoNotIndexedError(f"Repository {repo.slug} has no indexed content yet")
        return self._vector_index(repo).as_retriever(
            similarity_top_k=top_k,
            sparse_top_k=top_k * _SPARSE_POOL_FACTOR,
            vector_store_query_mode="hybrid",
        )

    def _vector_index(self, repo: RepoRef) -> VectorStoreIndex:
        store = QdrantVectorStore(
            collection_name(repo),
            client=self._client,
            enable_hybrid=True,
            sparse_doc_fn=self._sparse.documents,
            sparse_query_fn=self._sparse.queries,
            sparse_config=models.SparseVectorParams(modifier=models.Modifier.IDF),
        )
        return VectorStoreIndex.from_vector_store(store, embed_model=self._embed_model)

    def get_manifest(self, repo: RepoRef) -> RepoManifest | None:
        points = self._client.retrieve(REGISTRY_COLLECTION, [_point_id(repo)], with_payload=True)
        return _manifest_from_payload(points[0].payload or {}) if points else None

    def list_manifests(self) -> list[RepoManifest]:
        manifests: list[RepoManifest] = []
        offset = None
        while True:
            points, offset = self._client.scroll(
                REGISTRY_COLLECTION, limit=100, offset=offset, with_payload=True
            )
            manifests.extend(_manifest_from_payload(p.payload or {}) for p in points)
            if offset is None:
                return sorted(manifests, key=lambda m: m.repo.slug)

    def save_manifest(self, manifest: RepoManifest) -> None:
        payload = {
            "slug": manifest.repo.slug,
            "branch": manifest.repo.branch,
            "file_hashes": manifest.file_hashes,
            "chunk_count": manifest.chunk_count,
            "indexed_at": manifest.indexed_at.isoformat(),
        }
        point = models.PointStruct(id=_point_id(manifest.repo), vector={}, payload=payload)
        self._client.upsert(REGISTRY_COLLECTION, [point])

    def delete_repo(self, repo: RepoRef) -> None:
        self._client.delete_collection(collection_name(repo))
        self._client.delete(REGISTRY_COLLECTION, models.PointIdsList(points=[_point_id(repo)]))


class QdrantRepoIndex:
    """`RepoIndex` implementation for one repository."""

    def __init__(
        self, store: QdrantStore, client: QdrantClient, repo: RepoRef, index: VectorStoreIndex
    ) -> None:
        self._store = store
        self._client = client
        self._repo = repo
        self._collection = collection_name(repo)
        self._index = index

    def load_manifest(self) -> RepoManifest | None:
        return self._store.get_manifest(self._repo)

    def save_manifest(self, manifest: RepoManifest) -> None:
        self._store.save_manifest(manifest)

    def delete_files(self, paths: Sequence[str]) -> None:
        if not paths or not self._client.collection_exists(self._collection):
            return
        selector = models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(key=_DOC_ID_KEY, match=models.MatchAny(any=list(paths)))
                ]
            )
        )
        self._client.delete(self._collection, selector)

    def add_nodes(self, nodes: Sequence[BaseNode]) -> None:
        self._index.insert_nodes(list(nodes))

    def count_chunks(self) -> int:
        if not self._client.collection_exists(self._collection):
            return 0
        return self._client.count(self._collection, exact=True).count


def _manifest_from_payload(payload: dict[str, Any]) -> RepoManifest:
    return RepoManifest(
        repo=parse_repo(payload["slug"], payload.get("branch")),
        file_hashes=dict(payload.get("file_hashes", {})),
        chunk_count=int(payload.get("chunk_count", 0)),
        indexed_at=datetime.fromisoformat(payload["indexed_at"]),
    )
