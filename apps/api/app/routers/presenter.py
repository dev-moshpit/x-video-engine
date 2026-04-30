"""Presenter / talking-head endpoints — Platform Phase 1.

  GET  /api/presenter/providers           availability matrix
  POST /api/presenter/render              enqueue a presenter render
  GET  /api/presenter/jobs/{job_id}       poll status
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
from app.db.models import PresenterJob
from app.db.session import DbSession
from app.services.presenter import (
    PresenterJobRequest,
    enqueue_presenter,
    make_presenter_job_id,
)


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


router = APIRouter(prefix="/api/presenter", tags=["presenter"])


# ─── Listing ───────────────────────────────────────────────────────────


class PresenterProviderOut(BaseModel):
    id: str
    name: str
    installed: bool
    install_hint: str
    error: str | None = None
    cache_path: str | None = None
    description: str = ""
    required_vram_gb: float = 0.0


class PresenterProvidersResponse(BaseModel):
    providers: list[PresenterProviderOut]
    installed: int
    total: int


@router.get("/providers", response_model=PresenterProvidersResponse)
def list_providers(_user: CurrentDbUser) -> PresenterProvidersResponse:
    from apps.worker.presenter import list_presenter_providers

    items = [
        PresenterProviderOut(**p.__dict__)
        for p in list_presenter_providers()
    ]
    return PresenterProvidersResponse(
        providers=items,
        installed=sum(1 for it in items if it.installed),
        total=len(items),
    )


# ─── Render ────────────────────────────────────────────────────────────


PresenterAspect = Literal["9:16", "1:1", "16:9"]
PresenterStatus = Literal["pending", "running", "complete", "failed"]


class PresenterRenderRequest(BaseModel):
    provider_id: str = Field(..., min_length=1, max_length=32)
    script: str = Field(..., min_length=1, max_length=4000)
    avatar_image_url: str = Field(..., min_length=1, max_length=1000)
    voice: Optional[str] = Field(None, max_length=64)
    voice_rate: str = Field("+0%", max_length=8)
    aspect_ratio: PresenterAspect = "9:16"
    headline: Optional[str] = Field(None, max_length=200)
    ticker: Optional[str] = Field(None, max_length=400)


class PresenterJobOut(BaseModel):
    job_id: str
    provider_id: str
    script: str
    avatar_image_url: str
    voice: Optional[str]
    voice_rate: str
    aspect_ratio: str
    headline: Optional[str]
    ticker: Optional[str]
    status: PresenterStatus
    progress: float
    output_url: Optional[str]
    error: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]


def _to_out(j: PresenterJob) -> PresenterJobOut:
    return PresenterJobOut(
        job_id=j.job_id,
        provider_id=j.provider_id,
        script=j.script,
        avatar_image_url=j.avatar_image_url,
        voice=j.voice,
        voice_rate=j.voice_rate,
        aspect_ratio=j.aspect_ratio,
        headline=j.headline,
        ticker=j.ticker,
        status=j.status,  # type: ignore[arg-type]
        progress=j.progress,
        output_url=j.output_url,
        error=j.error,
        started_at=j.started_at,
        completed_at=j.completed_at,
    )


@router.post("/render", response_model=PresenterJobOut, status_code=201)
def render(
    body: PresenterRenderRequest,
    user: CurrentDbUser,
    db: DbSession,
) -> PresenterJobOut:
    from apps.worker.presenter import (
        get_presenter_provider,
    )
    from apps.worker.presenter.provider import UnknownPresenter

    try:
        provider = get_presenter_provider(body.provider_id)
    except UnknownPresenter as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e

    info = provider.info
    if not info.installed:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"presenter provider '{body.provider_id}' is not installed: "
            f"{info.error or ''} — install hint: {info.install_hint}",
        )

    job_id = make_presenter_job_id()
    row = PresenterJob(
        user_id=user.id,
        job_id=job_id,
        provider_id=body.provider_id,
        script=body.script,
        avatar_image_url=body.avatar_image_url,
        voice=body.voice,
        voice_rate=body.voice_rate,
        aspect_ratio=body.aspect_ratio,
        headline=body.headline,
        ticker=body.ticker,
        status="pending",
        progress=0.0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    enqueue_presenter(PresenterJobRequest(
        job_id=job_id,
        user_id=str(user.id),
        provider_id=body.provider_id,
        script=body.script,
        avatar_image_url=body.avatar_image_url,
        voice=body.voice,
        voice_rate=body.voice_rate,
        aspect_ratio=body.aspect_ratio,
        headline=body.headline,
        ticker=body.ticker,
    ))
    return _to_out(row)


@router.get("/jobs/{job_id}", response_model=PresenterJobOut)
def get_job(
    job_id: str,
    user: CurrentDbUser,
    db: DbSession,
) -> PresenterJobOut:
    row = db.execute(
        select(PresenterJob).where(PresenterJob.job_id == job_id)
    ).scalar_one_or_none()
    if row is None or row.user_id != user.id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "presenter job not found",
        )
    return _to_out(row)
