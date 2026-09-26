"""Content hashing and file-level diffing that make re-ingestion incremental."""

import hashlib
from dataclasses import dataclass


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FileDiff:
    added: list[str]
    changed: list[str]
    removed: list[str]
    unchanged: list[str]

    @property
    def to_index(self) -> list[str]:
        return self.added + self.changed


def diff_hashes(indexed: dict[str, str], current: dict[str, str]) -> FileDiff:
    """Compares `{path: hash}` of the stored index with the freshly downloaded files."""
    return FileDiff(
        added=sorted(path for path in current if path not in indexed),
        changed=sorted(p for p, h in current.items() if p in indexed and indexed[p] != h),
        removed=sorted(path for path in indexed if path not in current),
        unchanged=sorted(p for p, h in current.items() if indexed.get(p) == h),
    )
