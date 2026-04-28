"""Project CRUD + plan preview endpoint.

Ownership rule: every endpoint that touches a project resolves it via
``_get_owned_project`` which 404s when the row doesn't exist OR when
it belongs to a different user. We deliberately don't 403 — that would
leak the existence of a project owned by someone else.

The /plan endpoint is the first place the api calls into
``xvideo.prompt_native``. It's the cheap path: deterministic,
sub-second, no GPU. Heavy rendering goes through PR 6's queue.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.auth.deps import CurrentDbUser
from app.db.models import Project, Render
from app.db.session import DbSession
from app.schemas.projects import (
    GeneratedPlan,
    PlanRequest,
    PlanResponse,
    ProjectCreate,
    ProjectDetailResponse,
    ProjectResponse,
    ProjectUpdate,
    RenderSummary,
)
from app.schemas.templates import (
    VALID_TEMPLATE_IDS,
    validate_template_input,
)
from app.services.plans import plans_for_project, template_supports_plan


router = APIRouter(prefix="/api/projects", tags=["projects"])


def _get_owned_project(
    db, user, project_id: uuid.UUID,
) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    return project


@router.post("", response_model=ProjectResponse,
              status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectCreate,
    user: CurrentDbUser,
    db: DbSession,
) -> ProjectResponse:
    if body.template not in VALID_TEMPLATE_IDS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"unknown template '{body.template}' — expected one of "
            f"{VALID_TEMPLATE_IDS}",
        )
    try:
        canonical_input = validate_template_input(
            body.template, body.template_input,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))

    project = Project(
        user_id=user.id,
        template=body.template,
        name=body.name,
        template_input=canonical_input,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return ProjectResponse.model_validate(project)


@router.get("", response_model=list[ProjectResponse])
def list_projects(
    user: CurrentDbUser, db: DbSession,
) -> list[ProjectResponse]:
    rows = db.execute(
        select(Project)
        .where(Project.user_id == user.id)
        .order_by(Project.created_at.desc())
    ).scalars().all()
    return [ProjectResponse.model_validate(p) for p in rows]


@router.get("/{project_id}", response_model=ProjectDetailResponse)
def get_project(
    project_id: uuid.UUID,
    user: CurrentDbUser,
    db: DbSession,
) -> ProjectDetailResponse:
    project = _get_owned_project(db, user, project_id)
    renders = db.execute(
        select(Render)
        .where(Render.project_id == project.id)
        .order_by(Render.started_at.desc())
    ).scalars().all()
    base = ProjectResponse.model_validate(project).model_dump()
    return ProjectDetailResponse(
        **base,
        renders=[RenderSummary.model_validate(r) for r in renders],
    )


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    user: CurrentDbUser,
    db: DbSession,
) -> ProjectResponse:
    project = _get_owned_project(db, user, project_id)
    if body.name is not None:
        project.name = body.name
    if body.template_input is not None:
        try:
            project.template_input = validate_template_input(
                project.template, body.template_input,
            )
        except ValueError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    db.commit()
    db.refresh(project)
    return ProjectResponse.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT,
                response_class=Response)
def delete_project(
    project_id: uuid.UUID,
    user: CurrentDbUser,
    db: DbSession,
) -> Response:
    project = _get_owned_project(db, user, project_id)
    db.delete(project)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{project_id}/plan", response_model=PlanResponse)
def generate_plan(
    project_id: uuid.UUID,
    body: PlanRequest,
    user: CurrentDbUser,
    db: DbSession,
) -> PlanResponse:
    """Plan-only preview. Cheap, sub-second, no GPU.

    Uses the project's stored ``template_input`` so the user can
    iterate on the form, save, and click Preview without re-sending
    the whole payload. Returns 422 for templates that don't have a
    plan stage (Voiceover, Auto-Captions go straight to render in
    PR 6 / 9).
    """
    project = _get_owned_project(db, user, project_id)
    if not template_supports_plan(project.template):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"template '{project.template}' has no plan preview — "
            f"render it directly via /api/projects/{project_id}/render",
        )

    raw_plans = plans_for_project(
        project,
        variations=body.variations,
        seed=body.seed,
        score_and_filter=body.score_and_filter,
    )
    plans = [GeneratedPlan(**p) for p in raw_plans]
    # Phase 4: pick the highest-scoring variation. Ties break on
    # earliest position so the generation order is preserved when
    # plans tied — matches what the operator sees scrolling the list.
    recommended_index: Optional[int] = None
    if plans:
        best = max(
            range(len(plans)),
            key=lambda i: (
                plans[i].score.get("total", 0.0)
                if isinstance(plans[i].score, dict)
                else 0.0
            ),
        )
        recommended_index = best
    return PlanResponse(plans=plans, recommended_index=recommended_index)
