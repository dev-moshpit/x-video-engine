"""Share preview links — Phase 13.

Surface:
  POST   /api/renders/{job_id}/share        owner creates / re-activates link
  DELETE /api/renders/{job_id}/share        owner disables current link
  GET    /api/renders/{job_id}/share        owner reads current link state
  GET    /api/public/renders/{token}        public read for sharing

Owner-scoped 404 is the dominant pattern — non-owners (or unauthenticated
callers, on the owner-side endpoints) get 404 instead of 403 so the
existence of a render is never leaked across users.

The public endpoint exposes only the final mp4 url + template + project
name + created_at — no user-identifying info, no render history, no
template_input. Inactive / expired tokens return 404.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.auth.deps import CurrentDbUser
from app.db.models import Project, Render, RenderShare
from app.db.session import DbSession
from app.schemas.render import RenderStage


router = APIRouter(tags=["shares"])


# ─── Schemas ────────────────────────────────────────────────────────────

class ShareCreateRequest(BaseModel):
    expires_at: Optional[datetime] = None


class ShareResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    render_id: uuid.UUID
    token: str
    is_active: bool
    expires_at: Optional[datetime] = None
    created_at: datetime


class PublicShareResponse(BaseModel):
    """Only the fields safe for an unauthenticated viewer to see."""
    final_mp4_url: str
    template: str
    project_name: Optional[str] = None
    created_at: datetime


# ─── Helpers ────────────────────────────────────────────────────────────

def _new_token() -> str:
    # 32-byte URL-safe → ~43 char base64. Fits in our String(64) column.
    return secrets.token_urlsafe(32)


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


def _is_share_live(share: RenderShare) -> bool:
    if not share.is_active:
        return False
    if share.expires_at is not None:
        # Sqlite drops timezone info on round-trip — coerce to UTC if naive.
        exp = share.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp <= datetime.now(timezone.utc):
            return False
    return True


# ─── Owner endpoints ────────────────────────────────────────────────────

@router.post(
    "/api/renders/{job_id}/share",
    response_model=ShareResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_share(
    job_id: str,
    body: ShareCreateRequest,
    user: CurrentDbUser,
    db: DbSession,
) -> ShareResponse:
    render = _get_owned_render_by_job(db, user, job_id)
    if render.stage != RenderStage.COMPLETE.value or not render.final_mp4_url:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "render is not complete — only completed renders can be shared",
        )

    existing = db.execute(
        select(RenderShare).where(RenderShare.render_id == render.id)
    ).scalars().first()
    if existing is not None:
        # Re-activate / refresh expiry on the existing link rather than
        # creating a second row — keeps the URL stable across toggles.
        existing.is_active = True
        existing.expires_at = body.expires_at
        db.commit()
        db.refresh(existing)
        return ShareResponse.model_validate(existing)

    share = RenderShare(
        render_id=render.id,
        user_id=user.id,
        token=_new_token(),
        is_active=True,
        expires_at=body.expires_at,
    )
    db.add(share)
    db.commit()
    db.refresh(share)
    return ShareResponse.model_validate(share)


@router.get("/api/renders/{job_id}/share", response_model=ShareResponse)
def get_share(
    job_id: str,
    user: CurrentDbUser,
    db: DbSession,
) -> ShareResponse:
    render = _get_owned_render_by_job(db, user, job_id)
    share = db.execute(
        select(RenderShare).where(RenderShare.render_id == render.id)
    ).scalars().first()
    if share is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no share link")
    return ShareResponse.model_validate(share)


@router.delete(
    "/api/renders/{job_id}/share",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_share(
    job_id: str,
    user: CurrentDbUser,
    db: DbSession,
) -> Response:
    render = _get_owned_render_by_job(db, user, job_id)
    share = db.execute(
        select(RenderShare).where(RenderShare.render_id == render.id)
    ).scalars().first()
    if share is None:
        # Idempotent — deleting an already-missing link succeeds.
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    share.is_active = False
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Public endpoint ────────────────────────────────────────────────────

@router.get(
    "/api/public/renders/{token}",
    response_model=PublicShareResponse,
)
def public_get_share(
    token: str, db: DbSession,
) -> PublicShareResponse:
    share = db.execute(
        select(RenderShare).where(RenderShare.token == token)
    ).scalars().first()
    if share is None or not _is_share_live(share):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "share not found")

    render = db.get(Render, share.render_id)
    if (
        render is None
        or render.stage != RenderStage.COMPLETE.value
        or not render.final_mp4_url
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "share not found")

    project = db.get(Project, render.project_id)
    return PublicShareResponse(
        final_mp4_url=render.final_mp4_url,
        template=project.template if project else "",
        project_name=project.name if project else None,
        created_at=render.completed_at or render.started_at,
    )
