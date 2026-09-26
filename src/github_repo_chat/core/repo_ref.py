"""Parses GitHub repository references and builds the URLs and ids derived from them."""

import re
from dataclasses import dataclass
from urllib.parse import quote

from github_repo_chat.core.errors import InvalidRepoError

_OWNER = r"[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}"
_NAME = r"[A-Za-z0-9._-]{1,100}"
# The name quantifier is lazy so that a trailing ".git" is stripped instead of kept in the name.
_REPO_PATTERN = re.compile(
    rf"^(?:(?:https?://)?(?:www\.)?github\.com/)?(?P<owner>{_OWNER})/(?P<name>{_NAME}?)"
    r"(?:\.git)?(?:/tree/(?P<branch>[^?#]+))?/?$"
)
_BRANCH_PATTERN = re.compile(r"^[A-Za-z0-9._/-]{1,255}$")
_ID_SEPARATOR = "--"


@dataclass(frozen=True)
class RepoRef:
    owner: str
    name: str
    branch: str | None = None

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def id(self) -> str:
        # GitHub owners cannot contain "--", so the first separator splits the id unambiguously.
        return f"{self.owner}{_ID_SEPARATOR}{self.name}"

    @property
    def ref(self) -> str:
        return self.branch or "HEAD"

    @property
    def archive_url(self) -> str:
        ref = f"refs/heads/{self.branch}" if self.branch else "HEAD"
        return f"https://codeload.github.com/{self.slug}/zip/{quote(ref)}"

    def blob_url(self, path: str, line: int | None = None) -> str:
        url = f"https://github.com/{self.slug}/blob/{quote(self.ref)}/{quote(path)}"
        return f"{url}#L{line}" if line else url


def parse_repo(value: str, branch: str | None = None) -> RepoRef:
    """Parses `owner/name` or a GitHub URL; an explicit `branch` wins over one in the URL."""
    match = _REPO_PATTERN.match(value.strip())
    if not match or match["name"] in {".", ".."}:
        raise InvalidRepoError(f"Not a GitHub repository: {value!r}")
    chosen = (branch or match["branch"] or "").strip().strip("/") or None
    if chosen is not None and (not _BRANCH_PATTERN.match(chosen) or ".." in chosen):
        raise InvalidRepoError(f"Invalid branch name: {chosen!r}")
    return RepoRef(match["owner"].lower(), match["name"].lower(), chosen)


def parse_repo_id(repo_id: str) -> RepoRef:
    """Inverse of `RepoRef.id` (the branch is not part of the id)."""
    owner, sep, name = repo_id.partition(_ID_SEPARATOR)
    if not sep:
        raise InvalidRepoError(f"Invalid repository id: {repo_id!r}")
    return parse_repo(f"{owner}/{name}")


def parse_repo_or_id(value: str) -> RepoRef:
    """Accepts either `owner/name` (or a URL) or a repository id."""
    return parse_repo(value) if "/" in value else parse_repo_id(value)
