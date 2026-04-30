"""Publishing target endpoints — Platform Phase 1.

  GET  /api/publishing/providers              providers + configured flag
  POST /api/publishing/youtube/upload         enqueue a YouTube upload
  GET  /api/publishing/jobs/{job_id}          poll status

Distinct from the existing ``/api/projects/{id}/publish-metadata``
which only returns *suggested copy*. This router is the actual upload
path; it lights up only when the operator configured the YouTube
OAuth env vars.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth.deps import CurrentDbUser
from app.db.models import PublishingJob
from app.db.session import DbSession
from app.services.publishing_targets import (
    PublishingJobRequest,
    enqueue_publishing,
    make_publishing_job_id,
)


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


router = APIRouter(prefix="/api/publishing", tags=["publishing"])


# ─── Listing ───────────────────────────────────────────────────────────


class PublishingProviderOut(BaseModel):
    id: str
    name: str
    configured: bool
    setup_hint: str
    error: str | None = None
    description: str = ""


class PublishingProvidersResponse(BaseModel):
    providers: list[PublishingProviderOut]
    configured: int
    total: int


@router.get("/providers", response_model=PublishingProvidersResponse)
def list_providers(_user: CurrentDbUser) -> PublishingProvidersResponse:
    from apps.worker.publishing import list_publishing_providers

    items = [
        PublishingProviderOut(**p.__dict__)
        for p in list_publishing_providers()
    ]
    return PublishingProvidersResponse(
        providers=items,
        configured=sum(1 for it in items if it.configured),
        total=len(items),
    )


# ─── YouTube upload ────────────────────────────────────────────────────


PublishStatus = Literal["pending", "running", "complete", "failed"]
YouTubePrivacy = Literal["public", "unlisted", "private"]


class YouTubeUploadRequest(BaseModel):
    video_url: str = Field(..., min_length=1, max_length=1000)
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field("", max_length=5000)
    tags: list[str] = Field(default_factory=list)
    privacy: YouTubePrivacy = "private"


class PublishingJobOut(BaseModel):
    job_id: str
    provider_id: str
    video_url: str
    title: str
    description: str
    tags: list[str]
    privacy: str
    status: PublishStatus
    external_id: Optional[str]
    external_url: Optional[str]
    error: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]


def _to_out(j: PublishingJob) -> PublishingJobOut:
    return PublishingJobOut(
        job_id=j.job_id,
        provider_id=j.provider_id,
        video_url=j.video_url,
        title=j.title,
        description=j.description,
        tags=list(j.tags or []),
        privacy=j.privacy,
        status=j.status,  # type: ignore[arg-type]
        external_id=j.external_id,
        external_url=j.external_url,
        error=j.error,
        started_at=j.started_at,
        completed_at=j.completed_at,
    )


def _enqueue_upload(
    *, provider_id: str,
    body: YouTubeUploadRequest,
    user,
    db,
) -> PublishingJobOut:
    """Common path: validate provider configured + insert row + enqueue."""
    from apps.worker.publishing import get_publishing_provider
    from apps.worker.publishing.provider import UnknownPublisher

    try:
        provider = get_publishing_provider(provider_id)
    except UnknownPublisher as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e

    info = provider.info
    if not info.configured:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"publishing provider '{provider_id}' is not configured: "
            f"{info.error or ''} — setup hint: {info.setup_hint}",
        )

    job_id = make_publishing_job_id()
    row = PublishingJob(
        user_id=user.id,
        job_id=job_id,
        provider_id=provider_id,
        video_url=body.video_url,
        title=body.title,
        description=body.description,
        tags=list(body.tags or []),
        privacy=body.privacy,
        status="pending",
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    enqueue_publishing(PublishingJobRequest(
        job_id=job_id,
        user_id=str(user.id),
        provider_id=provider_id,
        video_url=body.video_url,
        title=body.title,
        description=body.description,
        tags=list(body.tags or []),
        privacy=body.privacy,
    ))
    return _to_out(row)


@router.post(
    "/youtube/upload",
    response_model=PublishingJobOut,
    status_code=201,
)
def upload_youtube(
    body: YouTubeUploadRequest,
    user: CurrentDbUser,
    db: DbSession,
) -> PublishingJobOut:
    return _enqueue_upload(
        provider_id="youtube", body=body, user=user, db=db,
    )


@router.get("/jobs/{job_id}", response_model=PublishingJobOut)
def get_job(
    job_id: str,
    user: CurrentDbUser,
    db: DbSession,
) -> PublishingJobOut:
    row = db.execute(
        select(PublishingJob).where(PublishingJob.job_id == job_id)
    ).scalar_one_or_none()
    if row is None or row.user_id != user.id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "publishing job not found",
        )
    return _to_out(row)
