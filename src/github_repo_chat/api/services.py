"""Dependency container wiring settings, storage, models and jobs, plus the ingestion runner."""

import logging
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Request
from qdrant_client import QdrantClient

from github_repo_chat.api.jobs import JobRegistry
from github_repo_chat.config import Settings
from github_repo_chat.core.archive import RepoArchive, download_archive
from github_repo_chat.core.chat import ChatEngine
from github_repo_chat.core.ingestion import ingest_repo
from github_repo_chat.core.repo_ref import RepoRef
from github_repo_chat.core.splitting import Splitter
from github_repo_chat.infra.qdrant_store import QdrantStore
from github_repo_chat.infra.tracing import Tracer, setup_tracing
from github_repo_chat.llm.factory import (
    build_embed_model,
    build_llm,
    build_reranker,
    build_sparse_encoders,
)

logger = logging.getLogger(__name__)

ArchiveFetcher = Callable[[RepoRef], bytes]


@dataclass
class Services:
    settings: Settings
    store: QdrantStore
    engine: ChatEngine
    tracer: Tracer
    jobs: JobRegistry
    fetch_archive: ArchiveFetcher

    def run_ingestion(self, repo: RepoRef) -> None:
        """Background task: every outcome, including failures, ends up in the job registry."""
        settings = self.settings
        try:
            self.jobs.update(repo.id, status="indexing", stage="downloading")
            archive = RepoArchive(self.fetch_archive(repo))
            splitter = Splitter(
                code_max_chars=settings.code_chunk_max_chars,
                code_chunk_lines=settings.code_chunk_lines,
                text_chunk_tokens=settings.text_chunk_tokens,
            )
            report = ingest_repo(
                repo,
                archive,
                self.store.index_for(repo),
                splitter,
                max_files=settings.max_files,
                max_file_bytes=settings.max_file_bytes,
                progress=lambda stage, done, total: self.jobs.update(
                    repo.id, stage=stage, done=done, total=total
                ),
            )
        except Exception as exc:
            logger.exception("Ingestion of %s failed", repo.slug)
            self.jobs.update(repo.id, status="failed", error=str(exc) or type(exc).__name__)
            return
        logger.info("Indexed %s: %s", repo.slug, report)
        self.jobs.update(repo.id, status="ready", stage="done")


def build_services(settings: Settings) -> Services:
    store = QdrantStore(
        QdrantClient(url=settings.qdrant_url),
        build_embed_model(settings),
        build_sparse_encoders(settings),
    )
    store.ensure_registry()
    engine = ChatEngine(
        build_llm(settings),
        top_k=settings.top_k,
        history_turns=settings.history_turns,
        reranker=build_reranker(settings),
    )

    def fetch(repo: RepoRef) -> bytes:
        return download_archive(
            repo, max_bytes=settings.max_archive_bytes, timeout_s=settings.download_timeout_s
        )

    return Services(settings, store, engine, setup_tracing(settings), JobRegistry(), fetch)


def get_services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services
