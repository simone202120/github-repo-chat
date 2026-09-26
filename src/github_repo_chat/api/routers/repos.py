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
    info = RepoInfo(
        id=repo.id,
        repo=repo.slug,
        branch=(job.repo if job else repo).branch,
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
    return _info(manifest.repo if manifest else repo, manifest, job)


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
    repos = {m.repo.id: m.repo for m in manifests.values()} | {
        repo_id: job.repo for repo_id, job in jobs.items() if repo_id not in manifests
    }
    return [
        _info(repos[repo_id], manifests.get(repo_id), jobs.get(repo_id))
        for repo_id in sorted(repos)
    ]


@router.get("/{repo_id}")
def get_repo(repo_id: str, services: ServicesDep) -> RepoInfo:
    return _find(services, repo_id)


@router.delete("/{repo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_repo(repo_id: str, services: ServicesDep) -> Response:
    info = _find(services, repo_id)
    if info.status in ("queued", "indexing"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"{info.repo} is being indexed")
    repo = parse_repo_id(repo_id)
    services.store.delete_repo(repo)
    services.jobs.discard(repo.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
