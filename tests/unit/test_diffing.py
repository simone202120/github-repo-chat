from github_repo_chat.core.diffing import content_hash, diff_hashes


def test_content_hash_is_stable_and_content_sensitive() -> None:
    assert content_hash("abc") == content_hash("abc")
    assert content_hash("abc") != content_hash("abd")
    assert len(content_hash("")) == 64


def test_diff_hashes_classifies_files() -> None:
    indexed = {"same.py": "1", "edited.py": "2", "gone.py": "3"}
    current = {"same.py": "1", "edited.py": "9", "new.py": "4"}
    diff = diff_hashes(indexed, current)
    assert diff.added == ["new.py"]
    assert diff.changed == ["edited.py"]
    assert diff.removed == ["gone.py"]
    assert diff.unchanged == ["same.py"]
    assert diff.to_index == ["new.py", "edited.py"]


def test_diff_hashes_first_ingestion_adds_everything() -> None:
    diff = diff_hashes({}, {"b.py": "1", "a.py": "2"})
    assert diff.added == ["a.py", "b.py"]
    assert diff.changed == diff.removed == diff.unchanged == []


def test_diff_hashes_empty_repository_removes_everything() -> None:
    diff = diff_hashes({"a.py": "1"}, {})
    assert diff.removed == ["a.py"]
    assert diff.to_index == []
