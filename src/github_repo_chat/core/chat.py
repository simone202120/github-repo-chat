"""Question answering: condense the follow-up, retrieve, rerank and answer with citations."""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.llms import LLM, ChatMessage, MessageRole
from llama_index.core.schema import MetadataMode, NodeWithScore

from github_repo_chat.core.citations import Source, build_sources, format_context
from github_repo_chat.core.repo_ref import RepoRef
from github_repo_chat.llm.prompts import (
    CONDENSE_TEMPLATE,
    NO_ANSWER,
    QA_TEMPLATE,
    SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)

Reranker = Callable[[str, list[str]], list[float]]
"""Scores each passage against the query; higher is more relevant."""

RERANK_POOL_FACTOR = 3


@dataclass(frozen=True)
class ChatTurn:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class Answer:
    text: str
    sources: list[Source]
    standalone_question: str


class ChatEngine:
    def __init__(
        self, llm: LLM, *, top_k: int, history_turns: int, reranker: Reranker | None = None
    ) -> None:
        self._llm = llm
        self._top_k = top_k
        self._history_turns = history_turns
        self._reranker = reranker

    @property
    def candidates(self) -> int:
        """How many chunks the retriever should return: a larger pool when reranking."""
        return self._top_k * RERANK_POOL_FACTOR if self._reranker else self._top_k

    def answer(
        self,
        repo: RepoRef,
        retriever: BaseRetriever,
        question: str,
        history: Sequence[ChatTurn] = (),
    ) -> Answer:
        recent = list(history)[-self._history_turns :] if self._history_turns else []
        standalone = self._condense(repo, question, recent)
        nodes = self._rerank(standalone, retriever.retrieve(standalone))
        if not nodes:
            return Answer(NO_ANSWER, [], standalone)
        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content=SYSTEM_PROMPT.format(repo=repo.slug)),
            *(ChatMessage(role=MessageRole(turn.role), content=turn.content) for turn in recent),
            ChatMessage(
                role=MessageRole.USER,
                content=QA_TEMPLATE.format(context=format_context(nodes), question=question),
            ),
        ]
        reply = self._llm.chat(messages).message.content or ""
        return Answer(reply.strip() or NO_ANSWER, build_sources(nodes), standalone)

    def _condense(self, repo: RepoRef, question: str, history: list[ChatTurn]) -> str:
        if not history:
            return question
        transcript = "\n".join(f"{turn.role}: {turn.content}" for turn in history)
        prompt = CONDENSE_TEMPLATE.format(repo=repo.slug, history=transcript, question=question)
        condensed = self._llm.complete(prompt).text.strip()
        return condensed or question

    def _rerank(self, query: str, nodes: list[NodeWithScore]) -> list[NodeWithScore]:
        if self._reranker is None or not nodes:
            return nodes[: self._top_k]
        passages = [n.node.get_content(metadata_mode=MetadataMode.EMBED) for n in nodes]
        scores = self._reranker(query, passages)
        rescored = [
            NodeWithScore(node=n.node, score=score) for n, score in zip(nodes, scores, strict=True)
        ]
        rescored.sort(key=lambda n: n.score or 0.0, reverse=True)
        return rescored[: self._top_k]
