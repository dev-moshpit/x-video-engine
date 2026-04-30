"""Video-model endpoints — Platform Phase 1.

  GET  /api/video-models                  → per-provider availability matrix
  POST /api/video-models/generate         → enqueue a real generation
  GET  /api/video-models/jobs/{job_id}    → poll status

The api imports ``apps.worker.video_models`` only to read each
provider's ``.info`` property — those probes are cheap and don't load
torch / diffusers. Heavy work happens in the worker.
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
from app.db.models import VideoGeneration
from app.db.session import DbSession
from app.services.video_models import (
    GenerationJobRequest,
    enqueue_generation,
    make_generation_job_id,
)


# Make ``apps.worker.*`` importable from the api process. The info
# probes don't need torch — only stdlib + Pathlib + os.environ.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


router = APIRouter(tags=["video_models"])


# ─── Listing ───────────────────────────────────────────────────────────


class VideoModelOut(BaseModel):
    id: str
    name: str
    mode: str
    required_vram_gb: float
    installed: bool
    install_hint: str
    error: str | None = None
    cache_path: str | None = None
    description: str = ""


class VideoModelsResponse(BaseModel):
    providers: list[VideoModelOut]
    installed: int
    total: int


@router.get("/api/video-models", response_model=VideoModelsResponse)
def list_video_models(_user: CurrentDbUser) -> VideoModelsResponse:
    from apps.worker.video_models import list_providers

    items = [VideoModelOut(**p.__dict__) for p in list_providers()]
    return VideoModelsResponse(
        providers=items,
        installed=sum(1 for it in items if it.installed),
        total=len(items),
    )


# ─── Generation ────────────────────────────────────────────────────────


GenAspect = Literal["9:16", "1:1", "16:9"]
GenStatus = Literal["pending", "running", "complete", "failed"]


class GenerationCreate(BaseModel):
    provider_id: str = Field(..., min_length=1, max_length=32)
    prompt: str = Field(..., min_length=1, max_length=4000)
    image_url: Optional[str] = Field(None, max_length=1000)
    duration_seconds: float = Field(4.0, gt=0, le=30.0)
    fps: int = Field(24, ge=8, le=60)
    aspect_ratio: GenAspect = "9:16"
    seed: Optional[int] = Field(None, ge=0, le=2**31 - 1)
    extra: dict = Field(default_factory=dict)


class GenerationOut(BaseModel):
    job_id: str
    provider_id: str
    prompt: str
    image_url: Optional[str]
    duration_seconds: float
    fps: int
    aspect_ratio: str
    seed: Optional[int]
    status: GenStatus
    progress: float
    output_url: Optional[str]
    error: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]


def _to_out(g: VideoGeneration) -> GenerationOut:
    return GenerationOut(
        job_id=g.job_id,
        provider_id=g.provider_id,
        prompt=g.prompt,
        image_url=g.image_url,
        duration_seconds=g.duration_seconds,
        fps=g.fps,
        aspect_ratio=g.aspect_ratio,
        seed=g.seed,
        status=g.status,  # type: ignore[arg-type]
        progress=g.progress,
        output_url=g.output_url,
        error=g.error,
        started_at=g.started_at,
        completed_at=g.completed_at,
    )


@router.post(
    "/api/video-models/generate",
    response_model=GenerationOut,
    status_code=201,
)
def generate(
    body: GenerationCreate,
    user: CurrentDbUser,
    db: DbSession,
) -> GenerationOut:
    """Enqueue a generation request against the named provider.

    Validates that the provider is registered + currently installed.
    A 503 with the install hint is returned if it isn't — we never
    silently substitute a different model.
    """
    from apps.worker.video_models import get_provider
    from apps.worker.video_models.provider import UnknownProvider

    try:
        provider = get_provider(body.provider_id)
    except UnknownProvider as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e

    info = provider.info
    if not info.installed:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"provider '{body.provider_id}' is not installed: "
            f"{info.error or ''} — install hint: {info.install_hint}",
        )
    if info.mode == "image-to-video" and not body.image_url:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"provider '{body.provider_id}' is image-to-video; image_url is required",
        )

    job_id = make_generation_job_id()
    row = VideoGeneration(
        user_id=user.id,
        job_id=job_id,
        provider_id=body.provider_id,
        prompt=body.prompt,
        image_url=body.image_url,
        duration_seconds=body.duration_seconds,
        fps=body.fps,
        aspect_ratio=body.aspect_ratio,
        seed=body.seed,
        extra=body.extra or {},
        status="pending",
        progress=0.0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    enqueue_generation(GenerationJobRequest(
        job_id=job_id,
        user_id=str(user.id),
        provider_id=body.provider_id,
        prompt=body.prompt,
        image_url=body.image_url,
        duration_seconds=body.duration_seconds,
        fps=body.fps,
        aspect_ratio=body.aspect_ratio,
        seed=body.seed,
        extra=body.extra or {},
    ))
    return _to_out(row)


@router.get(
    "/api/video-models/jobs/{job_id}",
    response_model=GenerationOut,
)
def get_generation(
    job_id: str,
    user: CurrentDbUser,
    db: DbSession,
) -> GenerationOut:
    row = db.execute(
        select(VideoGeneration).where(VideoGeneration.job_id == job_id)
    ).scalar_one_or_none()
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "generation not found")
    return _to_out(row)
