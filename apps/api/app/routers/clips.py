"""AI Clipper endpoints — Platform Phase 1.

Three endpoints power the /clips experience:

  POST /api/clips/analyze        kick off transcribe + score
  GET  /api/clips/{job_id}        poll status / read moments
  POST /api/clips/{job_id}/export queue an mp4 export of one moment

Auth: every endpoint requires the Clerk bearer + the lazy-upserted
DB user. ``analyze`` and ``export`` enqueue jobs against the worker;
``GET`` is a pure DB read so the frontend can poll cheaply.

Faster-whisper / ffmpeg are not loaded by the api process — they run
in the worker. The api just shapes payloads.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth.deps import CurrentDbUser
from app.db.models import ClipArtifact, ClipJob
from app.db.session import DbSession
from app.services.clipper import (
    ClipAnalyzeRequest,
    ClipExportRequest,
    enqueue_analyze,
    enqueue_export,
    make_job_id,
)


router = APIRouter(prefix="/api/clips", tags=["clips"])


# ─── Wire types ────────────────────────────────────────────────────────


SourceKind = Literal["video", "audio"]
ClipAspect = Literal["9:16", "1:1", "16:9"]
ClipStatus = Literal["pending", "running", "complete", "failed"]


class AnalyzeRequest(BaseModel):
    source_url: str = Field(..., min_length=1, max_length=1000)
    source_kind: SourceKind = "video"
    language: str = Field("auto", min_length=2, max_length=8)


class MomentOut(BaseModel):
    """One scored moment as the api ships it to the frontend."""
    moment_id: str
    start: float
    end: float
    duration: float
    text: str
    score: float
    score_breakdown: dict
    notes: list[str] = []


class ClipJobOut(BaseModel):
    job_id: str
    status: ClipStatus
    progress: float
    source_url: str
    source_kind: str
    language: str
    duration_sec: Optional[float]
    transcript_text: Optional[str]
    moments: list[MomentOut]
    error: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]


class ExportRequest(BaseModel):
    moment_id: str = Field(..., min_length=1, max_length=32)
    aspect: ClipAspect = "9:16"
    captions: bool = True


class ClipArtifactOut(BaseModel):
    id: uuid.UUID
    moment_id: str
    start_sec: float
    end_sec: float
    aspect: str
    captions: bool
    url: Optional[str]
    status: ClipStatus
    error: Optional[str]
    created_at: datetime


# ─── Helpers ───────────────────────────────────────────────────────────


def _to_moment_out(m: dict) -> MomentOut:
    """Translate a serialized moment+score dict from the worker to wire."""
    return MomentOut(
        moment_id=m.get("moment_id", "m000"),
        start=float(m.get("start", 0.0)),
        end=float(m.get("end", 0.0)),
        duration=float(m.get("duration", max(0.0, m.get("end", 0.0) - m.get("start", 0.0)))),
        text=m.get("text", ""),
        score=float(m.get("score", 0.0)),
        score_breakdown=m.get("score_breakdown", {}),
        notes=list(m.get("notes", []) or []),
    )


def _job_to_out(job: ClipJob) -> ClipJobOut:
    moments = [_to_moment_out(m) for m in (job.moments or [])]
    moments.sort(key=lambda m: m.score, reverse=True)
    return ClipJobOut(
        job_id=job.job_id,
        status=job.status,  # type: ignore[arg-type]
        progress=job.progress,
        source_url=job.source_url,
        source_kind=job.source_kind,
        language=job.language,
        duration_sec=job.duration_sec,
        transcript_text=job.transcript_text,
        moments=moments,
        error=job.error,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


def _ensure_owned(db, job_id: str, user_id) -> ClipJob:
    job = db.execute(
        select(ClipJob).where(ClipJob.job_id == job_id)
    ).scalar_one_or_none()
    if job is None or job.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "clip job not found")
    return job


# ─── Endpoints ─────────────────────────────────────────────────────────


@router.post("/analyze", response_model=ClipJobOut, status_code=201)
def analyze_clip(
    body: AnalyzeRequest,
    user: CurrentDbUser,
    db: DbSession,
) -> ClipJobOut:
    """Kick off transcript + segmentation + scoring in the worker."""
    job_id = make_job_id()
    job = ClipJob(
        user_id=user.id,
        job_id=job_id,
        source_url=body.source_url,
        source_kind=body.source_kind,
        language=body.language,
        status="pending",
        progress=0.0,
        moments=[],
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    enqueue_analyze(ClipAnalyzeRequest(
        job_id=job_id,
        user_id=str(user.id),
        source_url=body.source_url,
        source_kind=body.source_kind,
        language=body.language,
    ))
    return _job_to_out(job)


@router.get("/{job_id}", response_model=ClipJobOut)
def get_clip_job(
    job_id: str,
    user: CurrentDbUser,
    db: DbSession,
) -> ClipJobOut:
    job = _ensure_owned(db, job_id, user.id)
    return _job_to_out(job)


@router.post(
    "/{job_id}/export",
    response_model=ClipArtifactOut,
    status_code=201,
)
def export_clip(
    job_id: str,
    body: ExportRequest,
    user: CurrentDbUser,
    db: DbSession,
) -> ClipArtifactOut:
    """Queue an mp4 export of one moment from a completed analyze job."""
    job = _ensure_owned(db, job_id, user.id)
    if job.status != "complete":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"clip job not yet complete (status={job.status})",
        )

    # Find the moment the user picked.
    moment = next(
        (m for m in (job.moments or []) if m.get("moment_id") == body.moment_id),
        None,
    )
    if moment is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"moment '{body.moment_id}' not found in job",
        )

    artifact = ClipArtifact(
        clip_job_id=job.id,
        moment_id=body.moment_id,
        start_sec=float(moment.get("start", 0.0)),
        end_sec=float(moment.get("end", 0.0)),
        aspect=body.aspect,
        captions=body.captions,
        status="pending",
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)

    enqueue_export(ClipExportRequest(
        artifact_id=str(artifact.id),
        job_id=job_id,
        user_id=str(user.id),
        source_url=job.source_url,
        moment=moment,
        aspect=body.aspect,
        captions=body.captions,
    ))
    return ClipArtifactOut(
        id=artifact.id,
        moment_id=artifact.moment_id,
        start_sec=artifact.start_sec,
        end_sec=artifact.end_sec,
        aspect=artifact.aspect,
        captions=artifact.captions,
        url=artifact.url,
        status=artifact.status,  # type: ignore[arg-type]
        error=artifact.error,
        created_at=artifact.created_at,
    )


@router.get("/{job_id}/artifacts", response_model=list[ClipArtifactOut])
def list_artifacts(
    job_id: str,
    user: CurrentDbUser,
    db: DbSession,
) -> list[ClipArtifactOut]:
    job = _ensure_owned(db, job_id, user.id)
    rows = db.execute(
        select(ClipArtifact)
        .where(ClipArtifact.clip_job_id == job.id)
        .order_by(ClipArtifact.created_at.desc())
    ).scalars().all()
    return [
        ClipArtifactOut(
            id=a.id,
            moment_id=a.moment_id,
            start_sec=a.start_sec,
            end_sec=a.end_sec,
            aspect=a.aspect,
            captions=a.captions,
            url=a.url,
            status=a.status,  # type: ignore[arg-type]
            error=a.error,
            created_at=a.created_at,
        )
        for a in rows
    ]


# Re-exports so tests can import the marker timestamps.
_ = datetime, timezone  # silence unused import in some linters
