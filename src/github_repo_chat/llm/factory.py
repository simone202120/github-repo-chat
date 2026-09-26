"""Builds the OpenRouter LLM, the FastEmbed embedding model and the optional reranker."""

from collections.abc import Iterable
from dataclasses import dataclass

from fastembed import SparseEmbedding, SparseTextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder
from llama_index.core.embeddings import BaseEmbedding
from llama_index.core.llms import LLM
from llama_index.embeddings.fastembed import FastEmbedEmbedding
from llama_index.llms.openrouter import OpenRouter
from llama_index.vector_stores.qdrant.utils import BatchSparseEncoding, SparseEncoderCallable

from github_repo_chat.config import Settings
from github_repo_chat.core.chat import Reranker

_CONTEXT_WINDOW = 128_000
_MAX_ANSWER_TOKENS = 1024


def build_llm(settings: Settings) -> LLM:
    return OpenRouter(
        model=settings.llm_model,
        api_key=settings.openrouter_api_key.get_secret_value(),
        api_base=settings.openrouter_base_url,
        temperature=settings.llm_temperature,
        max_tokens=_MAX_ANSWER_TOKENS,
        context_window=_CONTEXT_WINDOW,
        # Asks OpenRouter to include the request cost in `usage`, shown in the UI and traces.
        additional_kwargs={"extra_body": {"usage": {"include": True}}},
    )


def build_embed_model(settings: Settings) -> BaseEmbedding:
    return FastEmbedEmbedding(model_name=settings.embed_model)


def build_reranker(settings: Settings) -> Reranker | None:
    """Cross-encoder reranker (ONNX, CPU), disabled when `RERANK_MODEL` is empty."""
    if not settings.rerank_model:
        return None
    encoder = TextCrossEncoder(model_name=settings.rerank_model)

    def rerank(query: str, passages: list[str]) -> list[float]:
        return list(encoder.rerank(query, passages))

    return rerank


@dataclass(frozen=True)
class SparseEncoders:
    """BM25 encoders for Qdrant hybrid search; queries and documents are weighted differently."""

    documents: SparseEncoderCallable
    queries: SparseEncoderCallable


def build_sparse_encoders(settings: Settings) -> SparseEncoders:
    model = SparseTextEmbedding(model_name=settings.sparse_model)

    def to_batch(embeddings: Iterable[SparseEmbedding]) -> BatchSparseEncoding:
        vectors = list(embeddings)
        return [v.indices.tolist() for v in vectors], [v.values.tolist() for v in vectors]

    return SparseEncoders(
        documents=lambda texts: to_batch(model.embed(texts)),
        queries=lambda texts: to_batch(model.query_embed(texts)),
    )
