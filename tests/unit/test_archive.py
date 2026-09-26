import httpx
import pytest

from github_repo_chat.core.archive import ArchiveEntry, RepoArchive, download_archive
from github_repo_chat.core.errors import ArchiveError, RepoNotFoundError
from github_repo_chat.core.repo_ref import RepoRef
from tests.fakes import make_zip

REPO = RepoRef("octo", "demo", "main")


def _download(handler, max_bytes: int = 1_000_000) -> bytes:
    return download_archive(
        REPO, max_bytes=max_bytes, timeout_s=5, transport=httpx.MockTransport(handler)
    )


def test_download_archive_returns_body_from_codeload() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=b"zip-bytes")

    assert _download(handler) == b"zip-bytes"
    assert seen == ["https://codeload.github.com/octo/demo/zip/refs/heads/main"]


def test_download_archive_maps_404_to_repo_not_found() -> None:
    with pytest.raises(RepoNotFoundError):
        _download(lambda _: httpx.Response(404))


def test_download_archive_maps_server_errors() -> None:
    with pytest.raises(ArchiveError):
        _download(lambda _: httpx.Response(502))


def test_download_archive_maps_network_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(ArchiveError):
        _download(handler)


def test_download_archive_aborts_when_too_large() -> None:
    with pytest.raises(ArchiveError, match="exceeds"):
        _download(lambda _: httpx.Response(200, content=b"x" * 101), max_bytes=100)


def test_repo_archive_strips_root_folder_and_skips_dirs() -> None:
    archive = RepoArchive(make_zip({"README.md": "hi", "src/a.py": "x = 1\n"}))
    assert sorted(archive.entries(), key=lambda e: e.path) == [
        ArchiveEntry("README.md", 2),
        ArchiveEntry("src/a.py", 6),
    ]
    assert archive.read("src/a.py") == b"x = 1\n"


def test_repo_archive_rejects_invalid_zip() -> None:
    with pytest.raises(ArchiveError):
        RepoArchive(b"not a zip")


def test_repo_archive_rejects_too_many_entries(monkeypatch) -> None:
    monkeypatch.setattr("github_repo_chat.core.archive.MAX_ENTRIES", 2)
    with pytest.raises(ArchiveError, match="more than 2 entries"):
        RepoArchive(make_zip({"a.py": "", "b.py": ""}))
