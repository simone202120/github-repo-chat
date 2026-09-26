"""Request and response models of the HTTP API, with input limits."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

JobStatus = Literal["queued", "indexing", "ready", "failed"]


class AddRepoRequest(BaseModel):
    url: str = Field(min_length=3, max_length=300, examples=["https://github.com/psf/requests"])
    branch: str | None = Field(default=None, max_length=255)


class RepoInfo(BaseModel):
    id: str
    repo: str
    branch: str | None
    status: JobStatus
    stage: str | None = None
    progress_done: int = 0
    progress_total: int = 0
    error: str | None = None
    file_count: int = 0
    chunk_count: int = 0
    indexed_at: datetime | None = None


class ChatMessageIn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class ChatRequest(BaseModel):
    repo: str = Field(min_length=3, max_length=300, description="Repository id or owner/name")
    question: str = Field(min_length=1, max_length=2000)
    history: list[ChatMessageIn] = Field(default_factory=list, max_length=20)


class SourceOut(BaseModel):
    number: int
    path: str
    symbol: str
    start_line: int
    url: str
    score: float | None


class UsageOut(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float | None


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceOut]
    standalone_question: str
    usage: UsageOut
    latency_ms: int
    trace_url: str | None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    qdrant: bool
    tracing: bool
