"""Ingestion use case: download, select, diff against the stored index, split and embed."""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from llama_index.core.schema import BaseNode

from github_repo_chat.core.archive import RepoArchive
from github_repo_chat.core.diffing import content_hash, diff_hashes
from github_repo_chat.core.file_filter import decode_text, is_candidate, language_for, priority
from github_repo_chat.core.repo_ref import RepoRef
from github_repo_chat.core.splitting import SourceFile, Splitter

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int, int], None]
"""Receives (stage, done, total) while a repository is being ingested."""


@dataclass(frozen=True)
class RepoManifest:
    repo: RepoRef
    file_hashes: dict[str, str]
    chunk_count: int
    indexed_at: datetime

    @property
    def file_count(self) -> int:
        return len(self.file_hashes)


@dataclass(frozen=True)
class IngestionReport:
    manifest: RepoManifest
    added: int
    changed: int
    removed: int
    unchanged: int


class RepoIndex(Protocol):
    """Storage of one repository's chunks plus the manifest used for incremental re-ingestion."""

    def load_manifest(self) -> RepoManifest | None: ...

    def save_manifest(self, manifest: RepoManifest) -> None: ...

    def delete_files(self, paths: Sequence[str]) -> None: ...

    def add_nodes(self, nodes: Sequence[BaseNode]) -> None: ...

    def count_chunks(self) -> int: ...


def select_files(archive: RepoArchive, *, max_files: int, max_file_bytes: int) -> list[SourceFile]:
    """Indexable files in priority order, capped at `max_files`."""
    candidates = sorted(
        (e.path for e in archive.entries() if is_candidate(e.path, e.size, max_file_bytes)),
        key=priority,
    )
    selected: list[SourceFile] = []
    for path in candidates:
        if len(selected) == max_files:
            logger.info("File cap reached: %d of %d candidates kept", max_files, len(candidates))
            break
        text = decode_text(path, archive.read(path))
        language = language_for(path)
        if text is not None and language is not None:
            selected.append(SourceFile(path, text, language))
    return selected


def ingest_repo(
    repo: RepoRef,
    archive: RepoArchive,
    index: RepoIndex,
    splitter: Splitter,
    *,
    max_files: int,
    max_file_bytes: int,
    batch_size: int = 64,
    progress: ProgressCallback | None = None,
) -> IngestionReport:
    report = progress or (lambda _stage, _done, _total: None)
    report("filtering", 0, 0)
    files = {
        f.path: f for f in select_files(archive, max_files=max_files, max_file_bytes=max_file_bytes)
    }
    current = {path: content_hash(f.text) for path, f in files.items()}
    previous = index.load_manifest()
    indexed = previous.file_hashes if previous else {}
    diff = diff_hashes(indexed, current)
    logger.info(
        "%s: %d added, %d changed, %d removed, %d unchanged",
        repo.slug,
        len(diff.added),
        len(diff.changed),
        len(diff.removed),
        len(diff.unchanged),
    )

    # Added files are deleted too: they may hold chunks from an earlier run that crashed midway.
    paths = diff.to_index + diff.removed
    index.delete_files(paths)
    kept = {path: indexed[path] for path in diff.unchanged}
    index.save_manifest(_manifest(repo, kept, index))

    nodes = []
    for done, path in enumerate(diff.to_index, start=1):
        nodes.extend(splitter.split(repo, files[path]))
        report("splitting", done, len(diff.to_index))
    for start in range(0, len(nodes), batch_size):
        index.add_nodes(nodes[start : start + batch_size])
        report("embedding", min(start + batch_size, len(nodes)), len(nodes))

    manifest = _manifest(repo, current, index)
    index.save_manifest(manifest)
    return IngestionReport(
        manifest=manifest,
        added=len(diff.added),
        changed=len(diff.changed),
        removed=len(diff.removed),
        unchanged=len(diff.unchanged),
    )


def _manifest(repo: RepoRef, hashes: dict[str, str], index: RepoIndex) -> RepoManifest:
    return RepoManifest(repo, hashes, index.count_chunks(), datetime.now(UTC))
