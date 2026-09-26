"""Splits repository files into chunks with citation metadata (path, symbol, start line, URL)."""

import logging
import re
from dataclasses import dataclass

import tree_sitter_language_pack
from llama_index.core import Document
from llama_index.core.node_parser import CodeSplitter, MarkdownNodeParser, SentenceSplitter
from llama_index.core.schema import NodeRelationship, RelatedNodeInfo, TextNode

from github_repo_chat.core.file_filter import CODE_EXTENSIONS
from github_repo_chat.core.repo_ref import RepoRef

logger = logging.getLogger(__name__)

META_REPO = "repo"
META_PATH = "path"
META_LANGUAGE = "language"
META_SYMBOL = "symbol"
META_START_LINE = "start_line"
META_URL = "url"
_NOT_EMBEDDED = [META_REPO, META_LANGUAGE, META_START_LINE, META_URL]

_CODE_LANGUAGES = set(CODE_EXTENSIONS.values())
_SENTENCE = re.compile(r"[^.!?]*(?:[.!?]+\s*|$)")
_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
_DEFINITIONS = [
    # Keyword definitions: def, class, func (with Go receiver), fn, struct, interface, ...
    re.compile(
        r"^\s*(?:(?:export|default|pub(?:\([\w:]+\))?|async|public|private|protected|internal"
        r"|static|final|abstract|open|override|data|sealed|unsafe)\s+)*"
        r"(?:def|class|function\*?|func|fn|interface|struct|enum|trait|impl|type|module|object"
        r"|record)\s+(?:\([^)]*\)\s*)?([A-Za-z_$][\w$]*)"
    ),
    # JavaScript/TypeScript arrow functions assigned to a constant.
    re.compile(
        r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?="
        r"\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*(?::[^=]+)?=>"
    ),
    # Java/C#/Kotlin-style methods declared with modifiers and a return type.
    re.compile(
        r"^\s*(?:(?:public|private|protected|internal|static|final|virtual|override|async"
        r"|abstract|synchronized)\s+)+[\w<>\[\],.?]+\s+([A-Za-z_]\w*)\s*\("
    ),
]


@dataclass(frozen=True)
class SourceFile:
    path: str
    text: str
    language: str


def _approx_tokens(text: str) -> list[str]:
    """Word/punctuation tokens: close enough to BPE counts and needs no tokenizer download."""
    return re.findall(r"\w+|[^\w\s]", text)


def _sentences(text: str) -> list[str]:
    """Regex sentence split, used instead of NLTK punkt (no data files, deterministic)."""
    return [sentence for sentence in _SENTENCE.findall(text) if sentence]


def _outline(file: SourceFile) -> list[tuple[int, str]]:
    """(line number, name) of every heading or definition, in file order."""
    if file.language == "markdown":
        patterns = [_HEADING]
    elif file.language in _CODE_LANGUAGES:
        patterns = _DEFINITIONS
    else:
        return []
    outline = []
    for number, line in enumerate(file.text.splitlines(), start=1):
        for pattern in patterns:
            if match := pattern.match(line):
                outline.append((number, match.group(1)))
                break
    return outline


def _symbol_for(outline: list[tuple[int, str]], start: int, end: int) -> str:
    """First definition inside the chunk, else the enclosing one that starts before it."""
    before = ""
    for line, name in outline:
        if line > end:
            break
        if line >= start:
            return name
        before = name
    return before


def _locate(text: str, chunk: str, cursor: int) -> int:
    """Offset of the chunk in the file; splitters may trim whitespace, so match its first line."""
    first_line = chunk.strip().splitlines()[0]
    offset = text.find(first_line, cursor)
    if offset < 0:
        offset = text.find(first_line)
    return offset if offset >= 0 else cursor


class Splitter:
    """Routes each file to the right LlamaIndex parser; not thread-safe (tree-sitter parsers)."""

    def __init__(self, *, code_max_chars: int, code_chunk_lines: int, text_chunk_tokens: int):
        self._code_max_chars = code_max_chars
        self._code_chunk_lines = code_chunk_lines
        self._markdown = MarkdownNodeParser()
        self._text = SentenceSplitter(
            chunk_size=text_chunk_tokens,
            chunk_overlap=text_chunk_tokens // 10,
            tokenizer=_approx_tokens,
            chunking_tokenizer_fn=_sentences,
        )
        self._code: dict[str, CodeSplitter] = {}

    def split(self, repo: RepoRef, file: SourceFile) -> list[TextNode]:
        outline = _outline(file)
        nodes = []
        cursor = 0
        for chunk in self._split_text(file):
            if not chunk.strip():
                continue
            cursor = _locate(file.text, chunk, cursor)
            start = file.text.count("\n", 0, cursor) + 1
            end = start + chunk.strip("\n").count("\n")
            node = TextNode(
                text=chunk,
                metadata={
                    META_REPO: repo.slug,
                    META_PATH: file.path,
                    META_LANGUAGE: file.language,
                    META_SYMBOL: _symbol_for(outline, start, end),
                    META_START_LINE: start,
                    META_URL: repo.blob_url(file.path, start),
                },
                excluded_embed_metadata_keys=_NOT_EMBEDDED,
                excluded_llm_metadata_keys=_NOT_EMBEDDED,
            )
            # The source document id is the path, so all chunks of a file can be deleted at once.
            node.relationships[NodeRelationship.SOURCE] = RelatedNodeInfo(node_id=file.path)
            nodes.append(node)
        return nodes

    def _split_text(self, file: SourceFile) -> list[str]:
        if file.language == "markdown":
            sections = self._markdown.get_nodes_from_documents([Document(text=file.text)])
            return [
                piece
                for section in sections
                for piece in self._text.split_text(section.get_content())
            ]
        code_splitter = self._code_splitter(file.language)
        if code_splitter is not None:
            try:
                return code_splitter.split_text(file.text)
            except ValueError:
                logger.warning("Cannot parse %s as %s, splitting as text", file.path, file.language)
        return self._text.split_text(file.text)

    def _code_splitter(self, language: str) -> CodeSplitter | None:
        if language not in _CODE_LANGUAGES:
            return None
        if language not in self._code:
            self._code[language] = CodeSplitter(
                language=language,
                chunk_lines=self._code_chunk_lines,
                max_chars=self._code_max_chars,
                parser=tree_sitter_language_pack.get_parser(language),
            )
        return self._code[language]
