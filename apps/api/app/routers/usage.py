"""Usage endpoint (PR 11).

GET /api/usage  →  aggregate counts per ``kind`` for the current user.
The frontend renders these as the dashboard's usage strip; Phase 3
billing reads the same data and applies tier limits.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.auth.deps import CurrentDbUser
from app.db.session import DbSession
from app.services.usage import aggregate_user_usage


router = APIRouter(prefix="/api", tags=["usage"])


class UsageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    render_seconds: float = Field(0.0, ge=0.0)
    exports: float = Field(0.0, ge=0.0)


@router.get("/usage", response_model=UsageResponse)
def get_usage(user: CurrentDbUser, db: DbSession) -> UsageResponse:
    totals = aggregate_user_usage(db, user.id)
    return UsageResponse(
        render_seconds=totals.get("render_seconds", 0.0),
        exports=totals.get("exports", 0.0),
    )
