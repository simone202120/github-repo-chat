"""Thread-safe in-memory registry of ingestion and deletion jobs, one active per repository."""

import threading
from dataclasses import dataclass, replace
from typing import Any

from github_repo_chat.api.schemas import JobStatus
from github_repo_chat.core.repo_ref import RepoRef


class JobConflictError(Exception):
    """The repository is already being indexed or deleted."""


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
        return self.status in ("queued", "indexing", "deleting")


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def start(self, repo: RepoRef) -> Job:
        return self._claim(repo, Job(repo))

    def begin_delete(self, repo: RepoRef) -> None:
        """Reserves the repository so no ingestion can start while its data is being dropped."""
        self._claim(repo, Job(repo, status="deleting"))

    def _claim(self, repo: RepoRef, job: Job) -> Job:
        with self._lock:
            current = self._jobs.get(repo.id)
            if current is not None and current.active:
                raise JobConflictError(f"{repo.slug} is busy ({current.status}), try again later")
            self._jobs[repo.id] = job
            return job

    def update(self, repo_id: str, **changes: Any) -> None:
        """No-op when the job is gone, so a background task never fails on bookkeeping."""
        with self._lock:
            if repo_id in self._jobs:
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
