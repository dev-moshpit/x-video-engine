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


class Subscription(Base):
    """Phase 3 — Stripe-backed paid plan.

    A user has at most one ``status='active'`` subscription. Tier-derived
    behavior (watermark, monthly credit grant, concurrency caps) is
    computed off the active subscription so a webhook update lands
    immediately. Free users have no row — :func:`effective_tier` returns
    "free" when nothing matches.
    """
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True,
    )
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, unique=True, index=True,
    )
    tier: Mapped[str] = mapped_column(
        String(16), nullable=False, default="free",
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active",
    )
    current_period_end: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=_utcnow, onupdate=_utcnow,
    )


class CreditLedger(Base):
    """Phase 3 — append-only credits journal.

    Balance = SUM(amount) over a user. Positive = grant, negative =
    consume. Reason is free-form so we can audit any odd entry by
    grepping the column ("monthly_grant", "render_consume:<job>",
    "topup", "stripe_invoice:<id>", "manual_adjust").
    """
    __tablename__ = "credits_ledger"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=_utcnow, index=True,
    )


class BrandKit(Base):
    """Phase 6 — per-user brand identity tokens.

    One row per user (unique on ``user_id``). Color tokens are short
    hex strings (``#1f6feb``) and apply to the panel-color templates;
    when fields are NULL the template falls back to its built-in palette
    so partial brand kits still work.
    """
    __tablename__ = "brand_kits"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True, index=True, nullable=False,
    )
    brand_color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)
    accent_color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)
    text_color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)
    logo_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    brand_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=_utcnow, onupdate=_utcnow,
    )

class ClipJob(Base):
    """AI Clipper analyze job — Phase 1 (Platform).

    The user uploads a long video / audio (via the existing presigned
    upload flow) and POSTs to ``/api/clips/analyze`` with the resulting
    URL. The api inserts one of these rows + enqueues the worker. The
    worker transcribes, segments, scores → writes ``moments`` JSON +
    flips status to "complete".

    Each row owns a ``ClipArtifact`` per exported clip the user picks
    afterwards.
    """
    __tablename__ = "clip_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    job_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False,
    )
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default="video",
    )
    language: Mapped[str] = mapped_column(
        String(8), nullable=False, default="auto",
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending",
    )
    progress: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0,
    )
    duration_sec: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True,
    )
    transcript_text: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )
    moments: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    artifacts: Mapped[list["ClipArtifact"]] = relationship(
        back_populates="job", cascade="all, delete-orphan",
    )


class ClipArtifact(Base):
    """One exported clip from a ``ClipJob``.

    Created when the user picks a moment + posts ``/api/clips/export``.
    The worker fills ``url`` after the export completes.
    """
    __tablename__ = "clip_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4,
    )
    clip_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clip_jobs.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    moment_id: Mapped[str] = mapped_column(String(32), nullable=False)
    start_sec: Mapped[float] = mapped_column(Float, nullable=False)
    end_sec: Mapped[float] = mapped_column(Float, nullable=False)
    aspect: Mapped[str] = mapped_column(String(8), nullable=False)
    captions: Mapped[bool] = mapped_column(nullable=False, default=True)
    url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending",
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow,
    )

    job: Mapped[ClipJob] = relationship(back_populates="artifacts")


class VideoGeneration(Base):
    """Direct video-model generation request — Platform Phase 1.

    Sits parallel to the template-based ``Render`` row but uses the
    provider abstraction in ``apps/worker/video_models``. Lets users
    pick a specific model (Wan 2.1, SVD, CogVideoX, …) and submit a
    pure prompt without going through one of the 10 templates.
    """
    __tablename__ = "video_generations"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    job_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False,
    )
    provider_id: Mapped[str] = mapped_column(
        String(32), nullable=False,
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[Optional[str]] = mapped_column(
        String(1000), nullable=True,
    )
    duration_seconds: Mapped[float] = mapped_column(
        Float, nullable=False, default=4.0,
    )
    fps: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    aspect_ratio: Mapped[str] = mapped_column(
        String(8), nullable=False, default="9:16",
    )
    seed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending",
    )
    progress: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0,
    )
    output_url: Mapped[Optional[str]] = mapped_column(
        String(1000), nullable=True,
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )


class PresenterJob(Base):
    """AI Presenter / talking-head job — Platform Phase 1.

    The user supplies an avatar image + a script + (optionally) a
    headline. The worker synthesizes voice, runs the chosen lipsync
    provider, and optionally overlays a news lower-third.
    """
    __tablename__ = "presenter_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    job_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False,
    )
    provider_id: Mapped[str] = mapped_column(
        String(32), nullable=False,
    )
    script: Mapped[str] = mapped_column(Text, nullable=False)
    avatar_image_url: Mapped[str] = mapped_column(
        String(1000), nullable=False,
    )
    voice: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    voice_rate: Mapped[str] = mapped_column(
        String(8), nullable=False, default="+0%",
    )
    aspect_ratio: Mapped[str] = mapped_column(
        String(8), nullable=False, default="9:16",
    )
    headline: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True,
    )
    ticker: Mapped[Optional[str]] = mapped_column(
        String(400), nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending",
    )
    progress: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0,
    )
    output_url: Mapped[Optional[str]] = mapped_column(
        String(1000), nullable=True,
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )


class PublishingJob(Base):
    """One upload-attempt to a social platform — Platform Phase 1.

    Created when the user clicks Publish for a render. The worker
    drains ``saas:publish:jobs``, calls the right provider's
    ``upload``, and writes ``external_id`` + ``external_url`` back.
    """
    __tablename__ = "publishing_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    job_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False,
    )
    provider_id: Mapped[str] = mapped_column(
        String(32), nullable=False,
    )
    video_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(
        Text, nullable=False, default="",
    )
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    privacy: Mapped[str] = mapped_column(
        String(16), nullable=False, default="private",
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending",
    )
    external_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True,
    )
    external_url: Mapped[Optional[str]] = mapped_column(
        String(1000), nullable=True,
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )


class EditorJob(Base):
    """Single-pass video editor job — Platform Phase 1.

    Trim + reframe + auto-caption + export, all in one ffmpeg pass.
    Mirrors the ``ClipArtifact`` shape but with explicit trim bounds
    + caption-language metadata so the worker doesn't need a separate
    Moment record.
    """
    __tablename__ = "editor_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    job_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False,
    )
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    trim_start: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    trim_end: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    aspect: Mapped[str] = mapped_column(
        String(8), nullable=False, default="9:16",
    )
    captions: Mapped[bool] = mapped_column(
        nullable=False, default=True,
    )
    caption_language: Mapped[str] = mapped_column(
        String(8), nullable=False, default="auto",
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending",
    )
    progress: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0,
    )
    output_url: Mapped[Optional[str]] = mapped_column(
        String(1000), nullable=True,
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )



class MediaAsset(Base):
    """Phase 2.5 — saved media library entry.

    Stored when the operator saves a Pexels/Pixabay search hit (or a
    direct upload) to their library. Adapters that take a ``*_url``
    field (split_video, roblox_rant, auto_captions video_url, etc.)
    can then receive the asset's ``url`` directly.
    """
    __tablename__ = "media_assets"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_asset_id: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(
        String(1000), nullable=True,
    )
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    orientation: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True,
    )
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    attribution: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow,
    )
