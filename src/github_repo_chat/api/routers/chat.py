"""Chat endpoint: answers a question about an indexed repository, traced in Langfuse."""

import time
from typing import Annotated

from fastapi import APIRouter, Depends

from github_repo_chat.api.schemas import ChatRequest, ChatResponse, SourceOut, UsageOut
from github_repo_chat.api.services import Services, get_services
from github_repo_chat.core.chat import ChatTurn
from github_repo_chat.core.errors import RepoNotIndexedError
from github_repo_chat.core.repo_ref import parse_repo_or_id

router = APIRouter(tags=["chat"])


@router.post("/chat")
def chat(body: ChatRequest, services: Annotated[Services, Depends(get_services)]) -> ChatResponse:
    repo = parse_repo_or_id(body.repo)
    manifest = services.store.get_manifest(repo)
    if manifest is None:
        raise RepoNotIndexedError(f"Repository {repo.slug} is not indexed")
    started = time.perf_counter()
    history = [ChatTurn(message.role, message.content) for message in body.history]
    retriever = services.store.retriever(manifest.repo, services.engine.candidates)
    with services.tracer.trace(
        "chat",
        input_data={"question": body.question, "history_turns": len(history)},
        metadata={"repo": repo.slug},
    ) as trace:
        answer = services.engine.answer(manifest.repo, retriever, body.question, history)
        trace.set_output({"answer": answer.text, "sources": [s.url for s in answer.sources]})
    return ChatResponse(
        answer=answer.text,
        sources=[SourceOut(**vars(source)) for source in answer.sources],
        standalone_question=answer.standalone_question,
        usage=UsageOut(**vars(answer.usage)),
        latency_ms=round((time.perf_counter() - started) * 1000),
        trace_url=trace.url,
    )
