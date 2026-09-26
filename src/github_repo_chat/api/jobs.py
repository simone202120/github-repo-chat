"""Thread-safe in-memory registry of ingestion jobs, one active job per repository."""

import threading
from dataclasses import dataclass, replace
from typing import Any

from github_repo_chat.api.schemas import JobStatus
from github_repo_chat.core.repo_ref import RepoRef


class JobConflictError(Exception):
    """An ingestion job for this repository is already queued or running."""


@dataclass(frozen=True)
class Job:
    repo: RepoRef
    status: JobStatus = "queued"
    stage: str | None = None
    done: int = 0
    total: int = 0
    error: str | None = None

    @property
    def active(self) -> bool:
        return self.status in ("queued", "indexing")


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def start(self, repo: RepoRef) -> Job:
        with self._lock:
            current = self._jobs.get(repo.id)
            if current is not None and current.active:
                raise JobConflictError(f"{repo.slug} is already being indexed")
            job = self._jobs[repo.id] = Job(repo)
            return job

    def update(self, repo_id: str, **changes: Any) -> None:
        with self._lock:
            self._jobs[repo_id] = replace(self._jobs[repo_id], **changes)

    def get(self, repo_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(repo_id)

    def all(self) -> list[Job]:
        with self._lock:
            return list(self._jobs.values())

    def discard(self, repo_id: str) -> None:
        with self._lock:
            self._jobs.pop(repo_id, None)
