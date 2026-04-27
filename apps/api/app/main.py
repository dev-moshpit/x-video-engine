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

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="x-video-engine SaaS API", version="0.1.0")


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="api", version=app.version)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "x-video-engine SaaS API",
        "version": app.version,
        "docs": "/docs",
    }
