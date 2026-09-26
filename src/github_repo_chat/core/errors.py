"""Domain exceptions raised by the core layer and translated to HTTP errors by the API."""


class RepoChatError(Exception):
    """Base class for all domain errors."""


class InvalidRepoError(RepoChatError):
    """The repository reference cannot be parsed."""


class RepoNotFoundError(RepoChatError):
    """The repository or branch does not exist or is not public."""


class ArchiveError(RepoChatError):
    """The repository archive cannot be downloaded or read."""


class RepoNotIndexedError(RepoChatError):
    """A question was asked about a repository that has not been indexed."""
