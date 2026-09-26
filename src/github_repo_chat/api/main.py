"""FastAPI entry point: builds the services at startup and maps domain errors to HTTP codes."""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from github_repo_chat.api.jobs import JobConflictError
from github_repo_chat.api.routers import chat, health, repos
from github_repo_chat.api.services import Services, build_services
from github_repo_chat.config import get_settings
from github_repo_chat.core.errors import InvalidRepoError, RepoChatError, RepoNotIndexedError

# Starlette picks the handler of the closest class in the exception's MRO, so the
# `RepoChatError` fallback only applies to domain errors without a more specific entry.
_STATUS_BY_ERROR: dict[type[Exception], int] = {
    InvalidRepoError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    RepoNotIndexedError: status.HTTP_404_NOT_FOUND,
    JobConflictError: status.HTTP_409_CONFLICT,
    RepoChatError: status.HTTP_400_BAD_REQUEST,
}


def _error_handler(code: int) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
    async def handle(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=code, content={"detail": str(exc)})

    return handle


def create_app(services: Services | None = None) -> FastAPI:
    """`services` is injected by tests; otherwise real ones are built from the environment."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logging.basicConfig(level=logging.INFO)
        app.state.services = services or build_services(get_settings())
        yield
        app.state.services.tracer.shutdown()

    app = FastAPI(title="github-repo-chat", version="0.1.0", lifespan=lifespan)
    for error, code in _STATUS_BY_ERROR.items():
        app.add_exception_handler(error, _error_handler(code))
    for module in (health, repos, chat):
        app.include_router(module.router)
    return app


app = create_app()
