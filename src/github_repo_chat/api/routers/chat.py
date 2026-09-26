"""Chat endpoint: answers a question about an indexed repository, traced in Langfuse."""

from typing import Annotated

from fastapi import APIRouter, Depends

from github_repo_chat.api.schemas import ChatRequest, ChatResponse, SourceOut
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
    history = [ChatTurn(message.role, message.content) for message in body.history]
    retriever = services.store.retriever(manifest.repo, services.engine.candidates)
    with services.tracer.trace(
        "chat",
        input_data={"question": body.question, "history_turns": len(history)},
        metadata={"repo": repo.slug},
    ) as set_output:
        answer = services.engine.answer(manifest.repo, retriever, body.question, history)
        set_output({"answer": answer.text, "sources": [s.url for s in answer.sources]})
    return ChatResponse(
        answer=answer.text,
        sources=[SourceOut(**vars(source)) for source in answer.sources],
        standalone_question=answer.standalone_question,
    )
