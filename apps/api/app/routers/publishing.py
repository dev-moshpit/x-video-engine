"""Publishing-metadata endpoint — Phase 7.

  GET /api/projects/{id}/publish-metadata
    → suggested title + description + hashtags + 2-3 alternate titles

Read-only: nothing is written to the DB. The frontend "Publish"
panel calls this once a render completes so the operator can copy
the suggested copy into TikTok / Reels / Shorts.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.auth.deps import CurrentDbUser
from app.db.models import Project
from app.db.session import DbSession
from app.services.publishing import generate_publish_metadata


router = APIRouter(prefix="/api/projects", tags=["publishing"])


class PublishMetadata(BaseModel):
    title: str
    description: str
    hashtags: list[str]
    alternates: list[str]


@router.get(
    "/{project_id}/publish-metadata",
    response_model=PublishMetadata,
)
def get_publish_metadata(
    project_id: uuid.UUID,
    user: CurrentDbUser,
    db: DbSession,
) -> PublishMetadata:
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    return PublishMetadata(**generate_publish_metadata(db, project))
