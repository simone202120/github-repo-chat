"""Downloads a repository zip from codeload and exposes its files without extracting them."""

import io
import logging
import zipfile
from dataclasses import dataclass

import httpx

from github_repo_chat.core.errors import ArchiveError, RepoNotFoundError
from github_repo_chat.core.repo_ref import RepoRef

logger = logging.getLogger(__name__)

# Bounds the work done on zip metadata before any filtering (real repositories stay far below).
MAX_ENTRIES = 100_000


@dataclass(frozen=True)
class ArchiveEntry:
    path: str
    size: int


def download_archive(
    repo: RepoRef,
    *,
    max_bytes: int,
    timeout_s: float,
    transport: httpx.BaseTransport | None = None,
) -> bytes:
    """Streams the archive into memory, aborting as soon as it exceeds `max_bytes`."""
    logger.info("Downloading %s", repo.archive_url)
    buffer = io.BytesIO()
    try:
        with (
            httpx.Client(timeout=timeout_s, follow_redirects=True, transport=transport) as client,
            client.stream("GET", repo.archive_url) as response,
        ):
            if response.status_code == httpx.codes.NOT_FOUND:
                raise RepoNotFoundError(f"Repository or branch not found: {repo.slug}@{repo.ref}")
            response.raise_for_status()
            for chunk in response.iter_bytes():
                buffer.write(chunk)
                if buffer.tell() > max_bytes:
                    raise ArchiveError(f"Archive of {repo.slug} exceeds {max_bytes} bytes")
    except httpx.HTTPError as exc:
        raise ArchiveError(f"Download of {repo.slug} failed: {exc}") from exc
    return buffer.getvalue()


class RepoArchive:
    """Read-only view of a codeload zip, with paths relative to the repository root."""

    def __init__(self, data: bytes) -> None:
        try:
            self._zip = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise ArchiveError("Downloaded archive is not a valid zip file") from exc
        if len(self._zip.infolist()) > MAX_ENTRIES:
            raise ArchiveError(f"Archive has more than {MAX_ENTRIES} entries")
        self._members = {
            path: info
            for info in self._zip.infolist()
            if not info.is_dir() and (path := _strip_root(info.filename))
        }

    def entries(self) -> list[ArchiveEntry]:
        return [ArchiveEntry(path, info.file_size) for path, info in self._members.items()]

    def read(self, path: str) -> bytes:
        return self._zip.read(self._members[path])


def _strip_root(name: str) -> str:
    """codeload wraps everything in a single `<repo>-<ref>/` folder."""
    return name.partition("/")[2]
