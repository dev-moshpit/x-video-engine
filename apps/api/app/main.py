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
    media,
    preferences,
    projects,
    renders,
    stripe_webhook,
    templates,
    uploads,
    usage,
    webhooks,
)


app = FastAPI(title="x-video-engine SaaS API", version="0.1.0")


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
