"""Rules deciding which repository files are indexed, in which order, and their language."""

import re
from pathlib import PurePosixPath

DOC_EXTENSIONS = {".md": "markdown", ".mdx": "markdown", ".rst": "rst", ".txt": "text"}
CODE_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".java": "java",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".kt": "kotlin",
    ".swift": "swift",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
}
EXCLUDED_DIRS = {
    "node_modules",
    "vendor",
    "dist",
    "build",
    "test",
    "tests",
    "spec",
    "specs",
    "__tests__",
    "__mocks__",
    "testdata",
    "fixtures",
    "site-packages",
}
# Test files, minified bundles, lockfiles and generated code, recognised by file name.
_EXCLUDED_NAME = re.compile(
    r"(^test_.*\.py$|_test\.(py|go)$|\.(test|spec)\.[jt]sx?$|Tests?\.(java|kt|cs|swift)$"
    r"|\.min\.[a-z]+$|\.lock$|_pb2(_grpc)?\.py$|\.pb\.go$|\.generated\.\w+$|\.d\.ts$)"
)
_GENERATED_MARKER = re.compile(r"(code generated .* do not edit|@generated|auto-generated)", re.I)
_MINIFIED_LINE_CHARS = 1000
_GENERATED_HEADER_CHARS = 1000
_SNIFF_BYTES = 8000


def is_readme(path: str) -> bool:
    return PurePosixPath(path).name.lower().startswith("readme")


def language_for(path: str) -> str | None:
    """Language of an indexable file, or None when the file type is not indexed."""
    suffix = PurePosixPath(path).suffix.lower()
    if suffix in CODE_EXTENSIONS:
        return CODE_EXTENSIONS[suffix]
    if suffix in DOC_EXTENSIONS:
        return DOC_EXTENSIONS[suffix]
    return "text" if is_readme(path) else None


def is_candidate(path: str, size: int, max_bytes: int) -> bool:
    """Path- and size-based rules, applied before reading the content."""
    parts = PurePosixPath(path).parts
    if size > max_bytes or not parts or language_for(path) is None:
        return False
    if any(part.startswith(".") or part.lower() in EXCLUDED_DIRS for part in parts[:-1]):
        return False
    return not _EXCLUDED_NAME.search(parts[-1])


def decode_text(path: str, data: bytes) -> str | None:
    """UTF-8 text of a file, or None for binaries and for minified or generated source code."""
    if b"\x00" in data[:_SNIFF_BYTES]:
        return None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if PurePosixPath(path).suffix.lower() not in CODE_EXTENSIONS:
        return text
    if _GENERATED_MARKER.search(text[:_GENERATED_HEADER_CHARS]):
        return None
    if any(len(line) > _MINIFIED_LINE_CHARS for line in text.splitlines()):
        return None
    return text


def priority(path: str) -> tuple[int, int, str]:
    """Sort key: READMEs, then docs, then source; shallower files first within each group."""
    depth = path.count("/")
    if is_readme(path):
        group = 0
    elif PurePosixPath(path).suffix.lower() in DOC_EXTENSIONS:
        group = 1
    else:
        group = 2
    return group, depth, path
