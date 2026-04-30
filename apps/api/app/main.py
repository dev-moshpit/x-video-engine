"""SaaS API service — FastAPI.

CPU-only. Imports the cheap plan-only surface of ``xvideo.prompt_native``
(``generate_video_plan``, ``score_plan``, ``audit_plan``,
``CAPTION_STYLES``) starting in PR 4. MUST NOT import the heavy renderer
(``xvideo.prompt_native.plan_renderer_bridge.render_video_plan``) — that
lives in apps/worker.

Run from the project root:

    py -3.11 -m uvicorn app.main:app --reload --port 8000 --app-dir apps/api

or via the pnpm script:

    pnpm dev:api
"""

from __future__ import annotations

import os
from datetime import datetime
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.auth.deps import CurrentDbUser
from app.routers import (
    billing,
    brand_kits,
    clips,
    editor,
    exports,
    insights,
    media,
    preferences,
    presenter,
    projects,
    publishing,
    publishing_targets,
    renders,
    saved_prompts,
    shares,
    stripe_webhook,
    system,
    templates,
    uploads,
    usage,
    video_models,
    webhooks,
)


app = FastAPI(title="x-video-engine SaaS API", version="0.1.0")


# ─── Dev no-docker convenience ──────────────────────────────────────────
# When XVE_DEV_FAKEREDIS=1 we swap the live Redis client for fakeredis on
# both queue producers (render + export). Lets the api boot + accept
# enqueues without a real Redis broker. The worker side won't see those
# jobs (separate process / fakeredis instance) — useful only for UI/CRUD
# testing without infra.
if os.environ.get("XVE_DEV_FAKEREDIS") == "1":
    try:
        import fakeredis as _fakeredis
        from app.services import clipper as _clipper_mod
        from app.services import editor as _editor_mod
        from app.services import exports as _exports_mod
        from app.services import presenter as _presenter_mod
        from app.services import publishing_targets as _publish_mod
        from app.services import queue as _queue_mod
        from app.services import video_models as _videogen_mod

        _shared = _fakeredis.FakeRedis(decode_responses=True)
        _queue_mod.set_redis(_shared)
        _exports_mod.set_redis(_shared)
        _clipper_mod.set_redis(_shared)
        _editor_mod.set_redis(_shared)
        _videogen_mod.set_redis(_shared)
        _presenter_mod.set_redis(_shared)
        _publish_mod.set_redis(_shared)
    except ImportError:
        pass


# CORS — the Next.js web app on :3000 (or the configured WEB_BASE_URL)
# calls this api with a Clerk JWT in the Authorization header. Browsers
# block such cross-origin requests unless we explicitly opt in.
_cors_origins = [
    o.strip()
    for o in os.environ.get(
        "WEB_BASE_URL", "http://localhost:3000"
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(webhooks.router)
app.include_router(templates.router)
app.include_router(projects.router)
app.include_router(renders.router)
app.include_router(uploads.router)
app.include_router(usage.router)
app.include_router(preferences.router)
app.include_router(media.router)
app.include_router(billing.router)
app.include_router(stripe_webhook.router)
app.include_router(publishing.router)
app.include_router(brand_kits.router)
app.include_router(saved_prompts.router)
app.include_router(insights.router)
app.include_router(shares.router)
app.include_router(exports.router)
app.include_router(system.router)
app.include_router(clips.router)
app.include_router(editor.router)
app.include_router(video_models.router)
app.include_router(presenter.router)
app.include_router(publishing_targets.router)


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Public liveness check — no auth, no DB."""
    return HealthResponse(status="ok", service="api", version=app.version)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "x-video-engine SaaS API",
        "version": app.version,
        "docs": "/docs",
    }


class MeResponse(BaseModel):
    """Authenticated principal + mirrored DB user record."""
    user_id: str
    db_user_id: uuid.UUID
    email: str | None
    tier: str
    created_at: datetime


@app.get("/api/me", response_model=MeResponse)
def me(db_user: CurrentDbUser) -> MeResponse:
    """Echo the authenticated user with both Clerk + internal IDs.

    The ``CurrentDbUser`` dep handles bearer verification + lazy
    upsert + mirroring the Clerk user_id into the local ``users``
    table, so by the time we return the row exists.
    """
    return MeResponse(
        user_id=db_user.clerk_user_id,
        db_user_id=db_user.id,
        email=db_user.email,
        tier=db_user.tier,
        created_at=db_user.created_at,
    )
