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
from pydantic import BaseModel, Field

from app.auth.deps import CurrentDbUser
from app.db.models import Project, Render
from app.db.session import DbSession
from app.routers.brand_kits import get_user_brand_kit
from app.schemas.projects import RenderSummary
from app.schemas.render import RenderJobRequest, RenderStage
from app.services import billing
from app.services.queue import enqueue_render


def _kit_payload(db, user_id) -> dict:
    """Project a BrandKit row into the dict shape the worker expects.

    Returns empty when the user has no kit row OR all the color/logo
    fields are NULL — saves the worker a no-op render path.
    """
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
    cleaned = {k: v for k, v in fields.items() if v}
    return cleaned


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

    # Phase 3: credit gate. Charge before enqueue so we don't accept a
    # job we can't bill for; refund happens on render-failure (worker
    # surfaces failed status, which a follow-up cron reconciles).
    cost = billing.render_cost_credits(project.template)
    try:
        billing.consume_credits(
            db, user.id, cost, reason=f"render_consume:{project.template}",
        )
    except billing.InsufficientCredits as exc:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            f"insufficient credits: {exc}. Upgrade your plan via "
            f"/api/billing/checkout to continue rendering.",
        )

    tier = billing.effective_tier(db, user.id)

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
            brand_kit=_kit_payload(db, user.id),
        )
    )

    return RenderSummary.model_validate(render)


@router.get("/renders/{render_id}", response_model=RenderSummary)
def get_render(
    render_id: uuid.UUID,
    user: CurrentDbUser,
    db: DbSession,
) -> RenderSummary:
    render = _get_owned_render(db, user, render_id)
    return RenderSummary.model_validate(render)


# ─── Phase 6: batch render ──────────────────────────────────────────────

class BatchRenderRequest(BaseModel):
    """Enqueue multiple renders of the same project in one click.

    Each render gets a fresh seed (the worker / engine handles the
    randomization downstream — we don't need to pre-randomize here).
    Phase 4's selection_learning naturally surfaces the best output
    once the batch finishes (operator stars the winner).
    """
    count: int = Field(..., ge=2, le=5)


@router.post(
    "/projects/{project_id}/render-batch",
    response_model=list[RenderSummary],
    status_code=status.HTTP_202_ACCEPTED,
)
def create_render_batch(
    project_id: uuid.UUID,
    body: BatchRenderRequest,
    user: CurrentDbUser,
    db: DbSession,
) -> list[RenderSummary]:
    """Enqueue ``body.count`` renders of one project.

    Charges the user upfront for the full batch — we deliberately
    don't atomic-refund the unconsumed renders if a mid-batch credit
    check would have failed. That's the only race-safe path without
    locking, and the alternative ("partial batch") is worse UX.
    """
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")

    cost = billing.render_cost_credits(project.template) * body.count
    try:
        billing.consume_credits(
            db, user.id, cost,
            reason=f"render_batch_consume:{project.template}:n={body.count}",
        )
    except billing.InsufficientCredits as exc:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            f"insufficient credits for batch: {exc}. "
            f"Each render costs {billing.render_cost_credits(project.template)} "
            f"credit(s); the batch needs {cost}. Upgrade or shrink the batch.",
        )

    tier = billing.effective_tier(db, user.id)
    kit = _kit_payload(db, user.id)
    out: list[RenderSummary] = []
    for _ in range(body.count):
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
        out.append(RenderSummary.model_validate(render))
    return out


def _get_owned_render(db, user, render_id: uuid.UUID) -> Render:
    render = db.get(Render, render_id)
    if render is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "render not found")
    project = db.get(Project, render.project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "render not found")
    return render


def _set_starred(
    db,
    user,
    render_id: uuid.UUID,
    value: bool | None,
) -> Render:
    render = _get_owned_render(db, user, render_id)
    render.starred = value
    db.commit()
    db.refresh(render)
    return render


@router.post("/renders/{render_id}/star", response_model=RenderSummary)
def star_render(
    render_id: uuid.UUID, user: CurrentDbUser, db: DbSession,
) -> RenderSummary:
    """Mark a render as starred — feeds the selection_learning loop."""
    return RenderSummary.model_validate(_set_starred(db, user, render_id, True))


@router.post("/renders/{render_id}/reject", response_model=RenderSummary)
def reject_render(
    render_id: uuid.UUID, user: CurrentDbUser, db: DbSession,
) -> RenderSummary:
    """Mark a render as rejected (negative signal for the learning loop)."""
    return RenderSummary.model_validate(_set_starred(db, user, render_id, False))


@router.delete("/renders/{render_id}/feedback", response_model=RenderSummary)
def clear_render_feedback(
    render_id: uuid.UUID, user: CurrentDbUser, db: DbSession,
) -> RenderSummary:
    """Clear any prior star/reject decision (return to ``None``)."""
    return RenderSummary.model_validate(_set_starred(db, user, render_id, None))
