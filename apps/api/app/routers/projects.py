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

from datetime import datetime, timezone

from app.auth.deps import CurrentDbUser
from app.db.models import Project, Render
from app.db.session import DbSession
from app.routers.brand_kits import get_user_brand_kit
from app.schemas.projects import (
    GeneratedPlan,
    PlanRequest,
    PlanResponse,
    ProjectCreate,
    ProjectDetailResponse,
    ProjectResponse,
    ProjectUpdate,
    RenderSummary,
    SmartGenerateRequest,
    SmartGenerateResponse,
)
from app.schemas.render import RenderJobRequest, RenderStage
from app.schemas.templates import (
    VALID_TEMPLATE_IDS,
    validate_template_input,
)
from app.services import billing
from app.services.plans import plans_for_project, template_supports_plan
from app.services.queue import enqueue_render
from app.services.selection_learning import (
    compute_plan_score_boost,
    compute_user_preferences,
)


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


# ─── Phase 8: smart generate ────────────────────────────────────────────

def _new_job_id() -> str:
    return uuid.uuid4().hex[:16]


def _kit_payload(db, user_id) -> dict:
    """Brand kit fields the worker needs — empty dict when no kit set."""
    kit = get_user_brand_kit(db, user_id)
    if kit is None:
        return {}
    fields = {
        "brand_color": kit.brand_color,
        "accent_color": kit.accent_color,
        "text_color": kit.text_color,
        "logo_url": kit.logo_url,
        "brand_name": kit.brand_name,
    }
    return {k: v for k, v in fields.items() if v}


@router.post(
    "/{project_id}/generate-smart",
    response_model=SmartGenerateResponse,
)
def generate_smart(
    project_id: uuid.UUID,
    body: SmartGenerateRequest,
    user: CurrentDbUser,
    db: DbSession,
) -> SmartGenerateResponse:
    """One-click "Generate Video" — generate N plan candidates, score
    each one (engine heuristic + user-preference boost), pick the best,
    then optionally enqueue ``render_top`` renders of it.

    For templates without a plan stage (e.g. ``voiceover``,
    ``auto_captions``), we skip directly to the render step using the
    project's saved ``template_input`` since there's no creative
    decision to make on a script-only template.
    """
    project = _get_owned_project(db, user, project_id)
    profile = compute_user_preferences(db, user.id)

    plans: list[GeneratedPlan] = []
    best_index = 0
    boosted_score = 0.0
    reasoning: list[str] = []

    if template_supports_plan(project.template):
        raw_plans = plans_for_project(
            project,
            variations=body.candidates,
            seed=body.seed,
            score_and_filter=True,
        )
        plans = [GeneratedPlan(**p) for p in raw_plans]
        if not plans:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "engine returned no plans",
            )

        # Score each candidate: engine heuristic + bounded user-history boost.
        scored: list[tuple[int, float, list[str]]] = []
        for i, p in enumerate(plans):
            base = (
                p.score.get("total", 0.0) if isinstance(p.score, dict) else 0.0
            )
            delta, why = compute_plan_score_boost(
                p.video_plan, profile, template=project.template,
            )
            scored.append((i, float(base) + delta, why))

        scored.sort(key=lambda t: t[1], reverse=True)
        best_index, boosted_score, reasoning = scored[0]
        if not reasoning:
            reasoning = [
                f"highest baseline score among {len(plans)} candidate(s) "
                f"(no user history to boost from yet)"
            ]

    # Optionally enqueue render(s) for the winner.
    rendered: list[RenderSummary] = []
    if body.render_top > 0:
        cost = billing.render_cost_credits(project.template) * body.render_top
        try:
            billing.consume_credits(
                db, user.id, cost,
                reason=f"smart_render:{project.template}:n={body.render_top}",
            )
        except billing.InsufficientCredits as exc:
            raise HTTPException(
                status.HTTP_402_PAYMENT_REQUIRED,
                f"insufficient credits: {exc}. Smart-generate would cost "
                f"{cost} credit(s). Upgrade your plan or set render_top=0 "
                f"to preview without rendering.",
            )

        tier = billing.effective_tier(db, user.id)
        kit = _kit_payload(db, user.id)
        for _ in range(body.render_top):
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
                    tier=tier,
                    brand_kit=kit,
                )
            )
            rendered.append(RenderSummary.model_validate(render))

    if not plans:
        # Direct-render template — synthesize a stub plan response so
        # the frontend has something to show. The video_plan dict is
        # left mostly empty; the score is a placeholder.
        stub = GeneratedPlan(
            video_plan={
                "title": project.name,
                "hook": "",
                "concept": "Direct-render template — no plan stage.",
                "scenes": [],
            },
            score={"total": 0.0, "notes": ["direct-render template"]},
            warnings=[],
        )
        plans = [stub]
        reasoning = ["template renders directly without a plan stage"]

    return SmartGenerateResponse(
        plans=plans,
        best_index=best_index,
        best_plan=plans[best_index],
        reasoning=reasoning,
        boosted_score=round(boosted_score, 2),
        rendered=rendered,
    )
