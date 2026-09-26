"""FastAPI entry point: builds the services at startup and maps domain errors to HTTP codes."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from github_repo_chat.api.jobs import JobConflictError
from github_repo_chat.api.routers import chat, health, repos
from github_repo_chat.api.services import Services, build_services
from github_repo_chat.config import get_settings
from github_repo_chat.core.errors import InvalidRepoError, RepoChatError, RepoNotIndexedError

_STATUS_BY_ERROR: dict[type[Exception], int] = {
    InvalidRepoError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    RepoNotIndexedError: status.HTTP_404_NOT_FOUND,
    JobConflictError: status.HTTP_409_CONFLICT,
    RepoChatError: status.HTTP_400_BAD_REQUEST,
}


async def _domain_error(_request: Request, exc: Exception) -> JSONResponse:
    code = next(c for error, c in _STATUS_BY_ERROR.items() if isinstance(exc, error))
    return JSONResponse(status_code=code, content={"detail": str(exc)})


def create_app(services: Services | None = None) -> FastAPI:
    """`services` is injected by tests; otherwise real ones are built from the environment."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logging.basicConfig(level=logging.INFO)
        app.state.services = services or build_services(get_settings())
        yield
        app.state.services.tracer.shutdown()

    app = FastAPI(title="github-repo-chat", version="0.1.0", lifespan=lifespan)
    for error in _STATUS_BY_ERROR:
        app.add_exception_handler(error, _domain_error)
    for module in (health, repos, chat):
        app.include_router(module.router)
    return app


app = create_app()
