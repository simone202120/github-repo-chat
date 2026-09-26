"""Repository endpoints: start ingestion, report status, list and delete indexed repositories."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status

from github_repo_chat.api.jobs import Job
from github_repo_chat.api.schemas import AddRepoRequest, RepoInfo
from github_repo_chat.api.services import Services, get_services
from github_repo_chat.core.ingestion import RepoManifest
from github_repo_chat.core.repo_ref import RepoRef, parse_repo, parse_repo_id

router = APIRouter(prefix="/repos", tags=["repos"])
ServicesDep = Annotated[Services, Depends(get_services)]


def _info(repo: RepoRef, manifest: RepoManifest | None, job: Job | None) -> RepoInfo:
    """A live job knows the branch being indexed; otherwise the manifest knows the indexed one."""
    source = job.repo if job else manifest.repo if manifest else repo
    info = RepoInfo(
        id=repo.id,
        repo=repo.slug,
        branch=source.branch,
        status=job.status if job else "ready",
    )
    if manifest is not None:
        info.file_count = manifest.file_count
        info.chunk_count = manifest.chunk_count
        info.indexed_at = manifest.indexed_at
    if job is not None:
        info.stage, info.progress_done, info.progress_total = job.stage, job.done, job.total
        info.error = job.error
    return info


def _find(services: Services, repo_id: str) -> RepoInfo:
    repo = parse_repo_id(repo_id)
    manifest = services.store.get_manifest(repo)
    job = services.jobs.get(repo.id)
    if manifest is None and job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Repository {repo.slug} is not indexed")
    return _info(repo, manifest, job)


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def add_repo(body: AddRepoRequest, background: BackgroundTasks, services: ServicesDep) -> RepoInfo:
    repo = parse_repo(body.url, body.branch)
    job = services.jobs.start(repo)
    background.add_task(services.run_ingestion, repo)
    return _info(repo, services.store.get_manifest(repo), job)


@router.get("")
def list_repos(services: ServicesDep) -> list[RepoInfo]:
    manifests = {m.repo.id: m for m in services.store.list_manifests()}
    jobs = {job.repo.id: job for job in services.jobs.all()}
    return [
        _info(parse_repo_id(repo_id), manifests.get(repo_id), jobs.get(repo_id))
        for repo_id in sorted(manifests.keys() | jobs.keys())
    ]


@router.get("/{repo_id}")
def get_repo(repo_id: str, services: ServicesDep) -> RepoInfo:
    return _find(services, repo_id)


@router.delete("/{repo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_repo(repo_id: str, services: ServicesDep) -> Response:
    _find(services, repo_id)
    repo = parse_repo_id(repo_id)
    services.jobs.begin_delete(repo)
    try:
        services.store.delete_repo(repo)
    finally:
        services.jobs.discard(repo.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
