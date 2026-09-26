"""In-memory test doubles shared by unit and API tests."""

import io
import zipfile
import zlib
from collections.abc import Sequence
from typing import Any

from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.llms import (
    ChatMessage,
    ChatResponse,
    CompletionResponse,
    CompletionResponseGen,
    CustomLLM,
    LLMMetadata,
    MessageRole,
)
from llama_index.core.schema import BaseNode, NodeWithScore, QueryBundle, TextNode
from pydantic import Field

from github_repo_chat.core.ingestion import RepoManifest


def make_zip(files: dict[str, str | bytes], root: str = "demo-main") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{root}/", "")
        for path, content in files.items():
            archive.writestr(f"{root}/{path}", content)
    return buffer.getvalue()


class InMemoryRepoIndex:
    def __init__(self) -> None:
        self.manifest: RepoManifest | None = None
        self.nodes: list[BaseNode] = []
        self.deleted: list[str] = []

    def load_manifest(self) -> RepoManifest | None:
        return self.manifest

    def save_manifest(self, manifest: RepoManifest) -> None:
        self.manifest = manifest

    def delete_files(self, paths: Sequence[str]) -> None:
        self.deleted.extend(paths)
        self.nodes = [n for n in self.nodes if n.ref_doc_id not in set(paths)]

    def add_nodes(self, nodes: Sequence[BaseNode]) -> None:
        self.nodes.extend(nodes)

    def count_chunks(self) -> int:
        return len(self.nodes)


class ScriptedLLM(CustomLLM):
    """Replies with canned responses in order and records every prompt it receives."""

    responses: list[str] = Field(default_factory=list)
    prompts: list[str] = Field(default_factory=list)
    usage: dict[str, Any] | None = None

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(model_name="scripted")

    def complete(self, prompt: str, formatted: bool = False, **kwargs: Any) -> CompletionResponse:
        self.prompts.append(prompt)
        text = self.responses.pop(0) if self.responses else ""
        if self.usage is None:
            return CompletionResponse(text=text)
        counts = {k: v for k, v in self.usage.items() if k.endswith("_tokens")}
        return CompletionResponse(text=text, raw={"usage": self.usage}, additional_kwargs=counts)

    def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponse:
        completion = self.complete(self.messages_to_prompt(messages))
        return ChatResponse(
            message=ChatMessage(role=MessageRole.ASSISTANT, content=completion.text),
            raw=completion.raw,
            additional_kwargs=completion.additional_kwargs,
        )

    def stream_complete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> CompletionResponseGen:
        raise NotImplementedError


class StaticRetriever(BaseRetriever):
    """Returns the same nodes for every query and records the queries."""

    def __init__(self, nodes: list[NodeWithScore]) -> None:
        super().__init__()
        self.nodes = nodes
        self.queries: list[str] = []

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        self.queries.append(query_bundle.query_str)
        return list(self.nodes)


def chunk(
    path: str, text: str, symbol: str = "", line: int = 1, score: float = 0.5
) -> NodeWithScore:
    node = TextNode(
        text=text,
        metadata={
            "path": path,
            "symbol": symbol,
            "start_line": line,
            "url": f"https://github.com/octo/demo/blob/HEAD/{path}#L{line}",
        },
    )
    return NodeWithScore(node=node, score=score)


def hashed_bag_of_words(texts: list[str]) -> tuple[list[list[int]], list[list[float]]]:
    """Deterministic stand-in for the BM25 encoder: one sparse dimension per distinct word."""
    indices, values = [], []
    for text in texts:
        words = sorted({zlib.crc32(w.lower().encode()) % 100_000 for w in text.split()})
        indices.append(words)
        values.append([1.0] * len(words))
    return indices, values
