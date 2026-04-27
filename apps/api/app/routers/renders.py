"""Render endpoints (PR 6).

  POST /api/projects/{id}/render   — enqueue a render job
  GET  /api/renders/{id}            — current status (frontend polls)

Owner-scoped: cross-user reads/writes return 404 to avoid leaking
existence (same convention as the projects router).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from app.auth.deps import CurrentDbUser
from app.db.models import Project, Render
from app.db.session import DbSession
from app.schemas.projects import RenderSummary
from app.schemas.render import RenderJobRequest, RenderStage
from app.services.queue import enqueue_render


router = APIRouter(prefix="/api", tags=["renders"])


def _new_job_id() -> str:
    return uuid.uuid4().hex[:16]


@router.post(
    "/projects/{project_id}/render",
    response_model=RenderSummary,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_render(
    project_id: uuid.UUID,
    user: CurrentDbUser,
    db: DbSession,
) -> RenderSummary:
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")

    job_id = _new_job_id()
    render = Render(
        project_id=project.id,
        job_id=job_id,
        stage=RenderStage.PENDING.value,
        progress=0.0,
        started_at=datetime.now(timezone.utc),
    )
    db.add(render)
    db.commit()
    db.refresh(render)

    enqueue_render(
        RenderJobRequest(
            job_id=job_id,
            user_id=user.clerk_user_id,
            project_id=str(project.id),
            template=project.template,
            template_input=project.template_input or {},
        )
    )

    return RenderSummary.model_validate(render)


@router.get("/renders/{render_id}", response_model=RenderSummary)
def get_render(
    render_id: uuid.UUID,
    user: CurrentDbUser,
    db: DbSession,
) -> RenderSummary:
    render = db.get(Render, render_id)
    if render is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "render not found")
    project = db.get(Project, render.project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "render not found")
    return RenderSummary.model_validate(render)
