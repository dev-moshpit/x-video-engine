"""SaaS DB schema (PR 3).

Five tables — the minimum to track who is rendering what:

  users         — mirror of Clerk user_id (lazy-upserted on /api/me;
                  also kept in sync via the Clerk webhook)
  projects      — a saved template input under a user
  renders       — a render-job execution attached to a project
  video_plans   — the VideoPlan emitted by the engine for a render
  usage         — per-user usage events (billing reads this in PR 3 / Phase 3)

Schema decisions:
- UUID primary keys (``sqlalchemy.Uuid`` — native UUID on Postgres,
  CHAR(32) on sqlite for tests).
- Timezone-aware ``DateTime`` everywhere; Python-side ``_utcnow`` default
  so we never store naive datetimes.
- ``sqlalchemy.JSON`` (dialect-agnostic) for ``template_input``,
  ``plan_json``, ``score_json``. Postgres will store as JSONB once we
  add an explicit JSONB column in a follow-up; for MVP JSON is enough.
- All relationship cascades are ``all, delete-orphan`` so deleting a
  user wipes their projects + renders + plans + usage.
- No ``latest_render_id`` cache on ``Project`` — query the renders
  table ordered by ``started_at`` instead. Cache when needed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4,
    )
    clerk_user_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False,
    )
    email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    tier: Mapped[str] = mapped_column(
        String(16), nullable=False, default="free",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow,
    )

    projects: Mapped[list["Project"]] = relationship(
        back_populates="user", cascade="all, delete-orphan",
    )
    usage: Mapped[list["Usage"]] = relationship(
        back_populates="user", cascade="all, delete-orphan",
    )


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    template: Mapped[str] = mapped_column(
        String(32), index=True, nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    template_input: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=_utcnow, onupdate=_utcnow,
    )

    user: Mapped[User] = relationship(back_populates="projects")
    renders: Mapped[list["Render"]] = relationship(
        back_populates="project", cascade="all, delete-orphan",
    )


class Render(Base):
    __tablename__ = "renders"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    job_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False,
    )
    stage: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending",
    )
    progress: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0,
    )
    final_mp4_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True,
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # PR 12: operator feedback. None = no decision, True = starred,
    # False = rejected. Read by selection_learning (PR 13).
    starred: Mapped[Optional[bool]] = mapped_column(nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    project: Mapped[Project] = relationship(back_populates="renders")
    video_plan: Mapped[Optional["VideoPlan"]] = relationship(
        back_populates="render", cascade="all, delete-orphan",
        uselist=False,
    )


class VideoPlan(Base):
    __tablename__ = "video_plans"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4,
    )
    render_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("renders.id", ondelete="CASCADE"),
        unique=True, index=True, nullable=False,
    )
    plan_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    score_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    prompt_hash: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False,
    )
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow,
    )

    render: Mapped[Render] = relationship(back_populates="video_plan")


class Usage(Base):
    __tablename__ = "usage"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    kind: Mapped[str] = mapped_column(
        String(32), index=True, nullable=False,
    )
    value: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=_utcnow, index=True,
    )

    user: Mapped[User] = relationship(back_populates="usage")
