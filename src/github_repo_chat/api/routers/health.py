"""Health endpoint: API liveness plus Qdrant reachability."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from github_repo_chat.api.schemas import HealthResponse
from github_repo_chat.api.services import Services, get_services

router = APIRouter(tags=["health"])


@router.get("/health")
def health(
    response: Response, services: Annotated[Services, Depends(get_services)]
) -> HealthResponse:
    qdrant = services.store.is_healthy()
    if not qdrant:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status="ok" if qdrant else "degraded",
        qdrant=qdrant,
        tracing=services.settings.tracing_enabled,
    )
