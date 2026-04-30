"""Export variants — Phase 13.5.

Surface:
  POST /api/renders/{job_id}/export-variant   create + enqueue an export
  GET  /api/renders/{job_id}/artifacts        list this render's exports

The body specifies a target aspect (9:16, 1:1, 16:9) and a captions
on/off toggle. The worker takes the existing final mp4, runs an
ffmpeg reframe pass, uploads the result, and writes the public URL
back into the artifact row.

We re-use the credit ledger: an export costs 0 credits today (it's a
remux of an asset the user already paid to render). If we add per-
second pricing later, this is the place to charge.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.auth.deps import CurrentDbUser
from app.db.models import Project, Render, RenderArtifact
from app.db.session import DbSession
from app.schemas.render import RenderStage
from app.services.exports import ExportJobRequest, enqueue_export


router = APIRouter(prefix="/api", tags=["exports"])


# ─── Schemas ────────────────────────────────────────────────────────────

VALID_ASPECTS = ("9:16", "1:1", "16:9")


class ExportVariantRequest(BaseModel):
    aspect: Literal["9:16", "1:1", "16:9"] = Field(...)
    captions: bool = True


class ArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    render_id: uuid.UUID
    kind: str
    aspect: str
    captions: bool
    url: str | None
    status: str
    error: str | None


# ─── Helpers ────────────────────────────────────────────────────────────

def _get_owned_render_by_job(db, user, job_id: str) -> Render:
    render = db.execute(
        select(Render).where(Render.job_id == job_id)
    ).scalars().first()
    if render is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "render not found")
    project = db.get(Project, render.project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "render not found")
    return render


# ─── Endpoints ──────────────────────────────────────────────────────────

@router.post(
    "/renders/{job_id}/export-variant",
    response_model=ArtifactResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_export_variant(
    job_id: str,
    body: ExportVariantRequest,
    user: CurrentDbUser,
    db: DbSession,
) -> ArtifactResponse:
    if body.aspect not in VALID_ASPECTS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"aspect must be one of {VALID_ASPECTS}",
        )

    render = _get_owned_render_by_job(db, user, job_id)
    if render.stage != RenderStage.COMPLETE.value or not render.final_mp4_url:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "render is not complete — only completed renders can be exported",
        )

    artifact = RenderArtifact(
        render_id=render.id,
        kind="export_variant",
        aspect=body.aspect,
        captions=body.captions,
        status="pending",
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)

    enqueue_export(
        ExportJobRequest(
            artifact_id=str(artifact.id),
            render_id=str(render.id),
            user_id=user.clerk_user_id,
            job_id=render.job_id,
            src_url=render.final_mp4_url,
            aspect=body.aspect,
            captions=body.captions,
        )
    )
    return ArtifactResponse.model_validate(artifact)


@router.get(
    "/renders/{job_id}/artifacts",
    response_model=list[ArtifactResponse],
)
def list_artifacts(
    job_id: str,
    user: CurrentDbUser,
    db: DbSession,
) -> list[ArtifactResponse]:
    render = _get_owned_render_by_job(db, user, job_id)
    rows = db.execute(
        select(RenderArtifact)
        .where(RenderArtifact.render_id == render.id)
        .order_by(RenderArtifact.created_at.desc())
    ).scalars().all()
    return [ArtifactResponse.model_validate(r) for r in rows]
