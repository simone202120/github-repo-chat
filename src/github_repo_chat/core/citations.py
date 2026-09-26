"""Turns retrieved chunks into numbered context for the prompt and cited sources for the reply."""

from dataclasses import dataclass

from llama_index.core.schema import MetadataMode, NodeWithScore

from github_repo_chat.core.splitting import META_PATH, META_START_LINE, META_SYMBOL, META_URL
from github_repo_chat.llm.prompts import CONTEXT_ENTRY_TEMPLATE


@dataclass(frozen=True)
class Source:
    number: int
    path: str
    symbol: str
    start_line: int
    url: str
    score: float | None


def build_sources(nodes: list[NodeWithScore]) -> list[Source]:
    """Numbers sources from 1 in retrieval order, matching the excerpt numbers in the prompt."""
    return [
        Source(
            number=number,
            path=str(item.node.metadata.get(META_PATH, "")),
            symbol=str(item.node.metadata.get(META_SYMBOL, "")),
            start_line=int(item.node.metadata.get(META_START_LINE, 1)),
            url=str(item.node.metadata.get(META_URL, "")),
            score=item.score,
        )
        for number, item in enumerate(nodes, start=1)
    ]


def _neutralize(text: str) -> str:
    """Stops repository content from closing the prompt delimiters and posing as instructions."""
    return text.replace("</excerpt", "<\\/excerpt").replace("</context", "<\\/context")


def format_context(nodes: list[NodeWithScore]) -> str:
    return "\n\n".join(
        CONTEXT_ENTRY_TEMPLATE.format(
            number=source.number,
            path=source.path,
            symbol=source.symbol,
            line=source.start_line,
            text=_neutralize(item.node.get_content(metadata_mode=MetadataMode.NONE)),
        )
        for source, item in zip(build_sources(nodes), nodes, strict=True)
    )
