"""SaaS API service — FastAPI.

CPU-only. MUST NOT import the heavy renderer
(``xvideo.prompt_native.plan_renderer_bridge`` or anything that
lazy-loads SDXL / torch). The api may import the plan-only surface
(``generate_video_plan``, ``score_plan``, ``audit_plan``) starting
in PR 4.

Run from the project root:

    py -3.11 -m uvicorn app.main:app --reload --port 8000 --app-dir apps/api

or via the pnpm script:

    pnpm dev:api
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.auth.clerk import CurrentUser
from app.db.session import DbSession
from app.routers import webhooks
from app.services.users import upsert_user_from_clerk

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
    user_id: str                # Clerk user_id
    db_user_id: uuid.UUID       # internal user.id (FK target everywhere)
    email: str | None
    tier: str
    created_at: datetime


@app.get("/api/me", response_model=MeResponse)
def me(user: CurrentUser, db: DbSession) -> MeResponse:
    """Echo the authenticated user; lazy-upsert into our ``users`` table.

    Returns 401 if the bearer token is missing, expired, or fails JWKS
    verification. On success, ensures a ``users`` row exists for this
    Clerk user_id (so subsequent endpoints can FK off ``user_id``).
    """
    db_user = upsert_user_from_clerk(
        db, clerk_user_id=user.user_id, email=user.email,
    )
    return MeResponse(
        user_id=user.user_id,
        db_user_id=db_user.id,
        email=db_user.email,
        tier=db_user.tier,
        created_at=db_user.created_at,
    )
