"""Editor endpoints — Platform Phase 1.

  POST /api/editor/process       enqueue a trim+caption+resize job
  GET  /api/editor/{job_id}      poll status

The user uploads through the existing presigned-PUT flow, then posts
the URL + edit knobs here. The worker drains ``saas:editor:jobs``,
runs the single-pass pipeline, uploads to R2, and writes
``output_url`` back into the row.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth.deps import CurrentDbUser
from app.db.models import EditorJob
from app.db.session import DbSession
from app.services.editor import (
    EditorJobRequest,
    enqueue_editor,
    make_editor_job_id,
)


router = APIRouter(prefix="/api/editor", tags=["editor"])


EditorAspect = Literal["9:16", "1:1", "16:9", "source"]
EditorStatus = Literal["pending", "running", "complete", "failed"]


class EditorRequest(BaseModel):
    source_url: str = Field(..., min_length=1, max_length=1000)
    trim_start: Optional[float] = Field(None, ge=0)
    trim_end: Optional[float] = Field(None, gt=0)
    aspect: EditorAspect = "9:16"
    captions: bool = True
    caption_language: str = Field("auto", min_length=2, max_length=8)


class EditorJobOut(BaseModel):
    job_id: str
    status: EditorStatus
    progress: float
    source_url: str
    trim_start: Optional[float]
    trim_end: Optional[float]
    aspect: str
    captions: bool
    caption_language: str
    output_url: Optional[str]
    error: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]


def _to_out(job: EditorJob) -> EditorJobOut:
    return EditorJobOut(
        job_id=job.job_id,
        status=job.status,  # type: ignore[arg-type]
        progress=job.progress,
        source_url=job.source_url,
        trim_start=job.trim_start,
        trim_end=job.trim_end,
        aspect=job.aspect,
        captions=job.captions,
        caption_language=job.caption_language,
        output_url=job.output_url,
        error=job.error,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


@router.post("/process", response_model=EditorJobOut, status_code=201)
def process(
    body: EditorRequest,
    user: CurrentDbUser,
    db: DbSession,
) -> EditorJobOut:
    if (
        body.trim_start is not None
        and body.trim_end is not None
        and body.trim_end <= body.trim_start
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "trim_end must be greater than trim_start",
        )

    job_id = make_editor_job_id()
    job = EditorJob(
        user_id=user.id,
        job_id=job_id,
        source_url=body.source_url,
        trim_start=body.trim_start,
        trim_end=body.trim_end,
        aspect=body.aspect,
        captions=body.captions,
        caption_language=body.caption_language,
        status="pending",
        progress=0.0,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    enqueue_editor(EditorJobRequest(
        job_id=job_id,
        user_id=str(user.id),
        source_url=body.source_url,
        trim_start=body.trim_start,
        trim_end=body.trim_end,
        aspect=body.aspect,
        captions=body.captions,
        caption_language=body.caption_language,
    ))
    return _to_out(job)


@router.get("/{job_id}", response_model=EditorJobOut)
def get_job(
    job_id: str,
    user: CurrentDbUser,
    db: DbSession,
) -> EditorJobOut:
    row = db.execute(
        select(EditorJob).where(EditorJob.job_id == job_id)
    ).scalar_one_or_none()
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "editor job not found")
    return _to_out(row)


# Re-export silenced
_ = uuid
