import pytest

from github_repo_chat.core.errors import InvalidRepoError
from github_repo_chat.core.repo_ref import RepoRef, parse_repo, parse_repo_id, parse_repo_or_id


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("psf/requests", RepoRef("psf", "requests")),
        ("  psf/requests  ", RepoRef("psf", "requests")),
        ("https://github.com/psf/requests", RepoRef("psf", "requests")),
        ("https://github.com/psf/requests/", RepoRef("psf", "requests")),
        ("https://www.github.com/PSF/Requests.git", RepoRef("psf", "requests")),
        ("github.com/psf/requests", RepoRef("psf", "requests")),
        ("https://github.com/psf/requests/tree/main", RepoRef("psf", "requests", "main")),
        ("https://github.com/a/b/tree/feature/x-1", RepoRef("a", "b", "feature/x-1")),
        ("user/user.github.io", RepoRef("user", "user.github.io")),
        ("my-org/some_repo.py", RepoRef("my-org", "some_repo.py")),
    ],
)
def test_parse_repo_accepts_supported_formats(value: str, expected: RepoRef) -> None:
    assert parse_repo(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "requests",
        "https://gitlab.com/a/b",
        "a/b/c",
        "-bad/repo",
        "bad-/repo",
        "ba--d/repo",
        "a/..",
        "a/b c",
        "https://github.com/a/b?x=1",
    ],
)
def test_parse_repo_rejects_invalid_references(value: str) -> None:
    with pytest.raises(InvalidRepoError):
        parse_repo(value)


def test_parse_repo_explicit_branch_overrides_url_branch() -> None:
    assert parse_repo("https://github.com/a/b/tree/dev", branch="main").branch == "main"


@pytest.mark.parametrize("branch", ["../etc", "a b", "x;rm", "a..b"])
def test_parse_repo_rejects_invalid_branch(branch: str) -> None:
    with pytest.raises(InvalidRepoError):
        parse_repo("a/b", branch=branch)


def test_parse_repo_blank_branch_means_default() -> None:
    assert parse_repo("a/b", branch="  ").branch is None


def test_repo_ref_urls_use_head_without_branch() -> None:
    ref = RepoRef("psf", "requests")
    assert ref.ref == "HEAD"
    assert ref.archive_url == "https://codeload.github.com/psf/requests/zip/HEAD"
    assert ref.blob_url("docs/a b.md", 12) == (
        "https://github.com/psf/requests/blob/HEAD/docs/a%20b.md#L12"
    )
    assert ref.blob_url("README.md") == "https://github.com/psf/requests/blob/HEAD/README.md"


def test_repo_ref_urls_use_branch() -> None:
    ref = RepoRef("a", "b", "feature/x")
    assert ref.archive_url == "https://codeload.github.com/a/b/zip/refs/heads/feature/x"
    assert ref.blob_url("x.py", 1) == "https://github.com/a/b/blob/feature/x/x.py#L1"


def test_repo_id_round_trips() -> None:
    ref = parse_repo("my-org/some--repo")
    assert ref.id == "my-org--some--repo"
    assert parse_repo_id(ref.id) == ref


def test_parse_repo_id_rejects_missing_separator() -> None:
    with pytest.raises(InvalidRepoError):
        parse_repo_id("nope")


@pytest.mark.parametrize("value", ["octo/demo", "octo--demo", "https://github.com/octo/demo"])
def test_parse_repo_or_id_accepts_slug_url_and_id(value: str) -> None:
    assert parse_repo_or_id(value) == RepoRef("octo", "demo")
