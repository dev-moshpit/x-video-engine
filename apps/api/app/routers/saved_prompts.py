"""Phase 9 — saved prompt presets.

  GET    /api/me/saved-prompts                list (most-recent first)
  POST   /api/me/saved-prompts                create from a saved input
  POST   /api/me/saved-prompts/{id}/use       duplicate into a fresh project
  PATCH  /api/me/saved-prompts/{id}           rename / overwrite input
  DELETE /api/me/saved-prompts/{id}           delete

Saved prompts are the retention hook: the user iterates on a
configuration once, saves it, then stamps out variations from the
dashboard with one click. The endpoints reuse the templates registry
for validation so a saved preset can never resurrect a stale or
deleted template id.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.auth.deps import CurrentDbUser
from app.db.models import Project, SavedPrompt
from app.db.session import DbSession
from app.schemas.projects import ProjectResponse
from app.schemas.templates import (
    VALID_TEMPLATE_IDS,
    validate_template_input,
)


router = APIRouter(prefix="/api/me/saved-prompts", tags=["saved-prompts"])


# ─── Schemas ────────────────────────────────────────────────────────────

class SavedPromptCreate(BaseModel):
    template: str = Field(..., min_length=1, max_length=32)
    label: str = Field(..., min_length=1, max_length=200)
    template_input: dict = Field(default_factory=dict)


class SavedPromptUpdate(BaseModel):
    label: Optional[str] = Field(None, min_length=1, max_length=200)
    template_input: Optional[dict] = None


class SavedPromptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    template: str
    label: str
    template_input: dict
    use_count: int
    last_used_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class UsePromptRequest(BaseModel):
    """Optional name override when stamping a saved prompt into a fresh project."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)


# ─── Helpers ────────────────────────────────────────────────────────────

def _get_owned(db, user, prompt_id: uuid.UUID) -> SavedPrompt:
    sp = db.get(SavedPrompt, prompt_id)
    if sp is None or sp.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "saved prompt not found")
    return sp


# ─── Endpoints ──────────────────────────────────────────────────────────

@router.get("", response_model=list[SavedPromptResponse])
def list_saved_prompts(
    user: CurrentDbUser, db: DbSession,
) -> list[SavedPromptResponse]:
    """Most-recently-used first; falls back to created_at when never used."""
    rows = db.execute(
        select(SavedPrompt)
        .where(SavedPrompt.user_id == user.id)
        .order_by(
            SavedPrompt.last_used_at.desc().nullslast(),
            SavedPrompt.created_at.desc(),
        )
    ).scalars().all()
    return [SavedPromptResponse.model_validate(r) for r in rows]


@router.post(
    "",
    response_model=SavedPromptResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_saved_prompt(
    body: SavedPromptCreate, user: CurrentDbUser, db: DbSession,
) -> SavedPromptResponse:
    if body.template not in VALID_TEMPLATE_IDS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"unknown template '{body.template}'",
        )
    try:
        canonical = validate_template_input(body.template, body.template_input)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))

    sp = SavedPrompt(
        user_id=user.id,
        template=body.template,
        label=body.label,
        template_input=canonical,
    )
    db.add(sp)
    db.commit()
    db.refresh(sp)
    return SavedPromptResponse.model_validate(sp)


@router.patch("/{prompt_id}", response_model=SavedPromptResponse)
def update_saved_prompt(
    prompt_id: uuid.UUID,
    body: SavedPromptUpdate,
    user: CurrentDbUser,
    db: DbSession,
) -> SavedPromptResponse:
    sp = _get_owned(db, user, prompt_id)
    if body.label is not None:
        sp.label = body.label
    if body.template_input is not None:
        try:
            sp.template_input = validate_template_input(
                sp.template, body.template_input,
            )
        except ValueError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    db.commit()
    db.refresh(sp)
    return SavedPromptResponse.model_validate(sp)


@router.delete(
    "/{prompt_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_saved_prompt(
    prompt_id: uuid.UUID, user: CurrentDbUser, db: DbSession,
) -> Response:
    sp = _get_owned(db, user, prompt_id)
    db.delete(sp)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{prompt_id}/use", response_model=ProjectResponse)
def use_saved_prompt(
    prompt_id: uuid.UUID,
    body: UsePromptRequest,
    user: CurrentDbUser,
    db: DbSession,
) -> ProjectResponse:
    """Stamp a saved prompt into a fresh project (the user can then
    iterate / render). Bumps the use_count + last_used_at so the
    dashboard can rank presets by recent activity."""
    sp = _get_owned(db, user, prompt_id)

    project = Project(
        user_id=user.id,
        template=sp.template,
        name=body.name or sp.label,
        template_input=dict(sp.template_input),
    )
    db.add(project)

    sp.use_count += 1
    sp.last_used_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(project)
    return ProjectResponse.model_validate(project)
