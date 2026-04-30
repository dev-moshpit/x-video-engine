"""System & model health endpoints — Phase 1 (Platform).

  GET /api/system/health   → infra probes (ffmpeg / redis / storage / gpu)
  GET /api/models/health   → per-model availability matrix

Both are authenticated reads. They never trigger downloads or model
loads — they only inspect what's already on disk and what python can
import. Safe to call from a settings page on every navigation.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.auth.deps import CurrentDbUser
from app.services.system_health import (
    models_health_snapshot,
    system_health_snapshot,
)


router = APIRouter(tags=["system"])


class ProbeOut(BaseModel):
    name: str
    ok: bool
    detail: str = ""
    error: str | None = None
    hint: str | None = None
    extra: dict = {}


class SystemHealthResponse(BaseModel):
    ok: bool
    probes: list[ProbeOut]


class ModelProbeOut(BaseModel):
    id: str
    name: str
    mode: str
    installed: bool
    required_vram_gb: float
    status: str
    error: str | None = None
    hint: str | None = None
    cache_path: str | None = None


class ModelsHealthResponse(BaseModel):
    models: list[ModelProbeOut]
    installed: int
    total: int


@router.get("/api/system/health", response_model=SystemHealthResponse)
def get_system_health(_user: CurrentDbUser) -> SystemHealthResponse:
    snap = system_health_snapshot()
    return SystemHealthResponse(**snap)


@router.get("/api/models/health", response_model=ModelsHealthResponse)
def get_models_health(_user: CurrentDbUser) -> ModelsHealthResponse:
    snap = models_health_snapshot()
    return ModelsHealthResponse(**snap)
