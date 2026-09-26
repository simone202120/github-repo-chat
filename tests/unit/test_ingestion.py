import pytest

from github_repo_chat.core.archive import RepoArchive
from github_repo_chat.core.ingestion import ingest_repo, select_files
from github_repo_chat.core.repo_ref import RepoRef
from github_repo_chat.core.splitting import Splitter
from tests.fakes import InMemoryRepoIndex, make_zip

REPO = RepoRef("octo", "demo")
FILES: dict[str, str | bytes] = {
    "README.md": "# Demo\n\nA demo project.\n\n## Install\n\npip install demo\n",
    "src/demo/core.py": "def add(a, b):\n    return a + b\n",
    "src/demo/util.py": "def slug(x):\n    return x.lower()\n",
    "tests/test_core.py": "def test_add():\n    assert True\n",
    "logo.png": b"\x89PNG\x00\x00",
    "bin/data.py": b"\x00\x01binary",
}


@pytest.fixture
def splitter() -> Splitter:
    return Splitter(code_max_chars=500, code_chunk_lines=40, text_chunk_tokens=128)


def _ingest(files, index, splitter, progress=None, max_files=100):
    return ingest_repo(
        REPO,
        RepoArchive(make_zip(files)),
        index,
        splitter,
        max_files=max_files,
        max_file_bytes=10_000,
        batch_size=2,
        progress=progress,
    )


def test_select_files_filters_and_prioritizes() -> None:
    selected = select_files(RepoArchive(make_zip(FILES)), max_files=10, max_file_bytes=10_000)
    assert [f.path for f in selected] == ["README.md", "src/demo/core.py", "src/demo/util.py"]
    assert selected[0].language == "markdown"


def test_select_files_caps_file_count() -> None:
    selected = select_files(RepoArchive(make_zip(FILES)), max_files=1, max_file_bytes=10_000)
    assert [f.path for f in selected] == ["README.md"]


def test_ingest_repo_first_run_indexes_everything(splitter: Splitter) -> None:
    index = InMemoryRepoIndex()
    events: list[tuple[str, int, int]] = []
    report = _ingest(FILES, index, splitter, progress=lambda *e: events.append(e))
    assert report.added == 3
    assert report.manifest.file_count == 3
    assert report.manifest.chunk_count == len(index.nodes) > 3
    assert {n.ref_doc_id for n in index.nodes} == {
        "README.md",
        "src/demo/core.py",
        "src/demo/util.py",
    }
    assert events[-1][0] == "embedding"
    assert events[-1][1] == events[-1][2] == len(index.nodes)


def test_ingest_repo_second_run_only_reembeds_changes(splitter: Splitter) -> None:
    index = InMemoryRepoIndex()
    _ingest(FILES, index, splitter)
    updated = {k: v for k, v in FILES.items() if k != "src/demo/util.py"}
    updated["src/demo/core.py"] = "def add(a, b):\n    return b + a\n"
    updated["docs/usage.md"] = "# Usage\n\nCall add.\n"
    index.deleted.clear()

    report = _ingest(updated, index, splitter)

    assert (report.added, report.changed, report.removed, report.unchanged) == (1, 1, 1, 1)
    assert sorted(index.deleted) == ["docs/usage.md", "src/demo/core.py", "src/demo/util.py"]
    paths = [n.ref_doc_id for n in index.nodes]
    assert paths.count("README.md") == 2
    assert "src/demo/util.py" not in paths
    assert set(report.manifest.file_hashes) == {"README.md", "docs/usage.md", "src/demo/core.py"}
    assert report.manifest.chunk_count == len(index.nodes)


def test_ingest_repo_unchanged_repo_embeds_nothing(splitter: Splitter) -> None:
    index = InMemoryRepoIndex()
    _ingest(FILES, index, splitter)
    before = list(index.nodes)
    report = _ingest(FILES, index, splitter)
    assert report.unchanged == 3
    assert report.added == report.changed == report.removed == 0
    assert index.nodes == before


class _FailingIndex(InMemoryRepoIndex):
    def add_nodes(self, nodes):
        raise RuntimeError("qdrant down")


def test_ingest_repo_failure_leaves_manifest_consistent(splitter: Splitter) -> None:
    index = _FailingIndex()
    with pytest.raises(RuntimeError):
        _ingest(FILES, index, splitter)
    assert index.manifest is not None
    assert index.manifest.file_hashes == {}
