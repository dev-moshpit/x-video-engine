"""Presigned-upload endpoint (PR 7).

POST /api/uploads/sign  →  presigned PUT URL the browser uses to upload
directly to R2 / MinIO. The api never streams the file body itself.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.auth.deps import CurrentDbUser
from app.services.storage import make_presigned_put


router = APIRouter(prefix="/api/uploads", tags=["uploads"])


class PresignRequest(BaseModel):
    kind: Literal["audio", "video", "image"]
    content_type: str = Field(..., min_length=1, max_length=120)
    expires_sec: int = Field(900, ge=30, le=3600)


class PresignResponse(BaseModel):
    url: str
    key: str
    method: Literal["PUT"]
    expires_in: int
    content_type: str


@router.post("/sign", response_model=PresignResponse)
def sign(
    body: PresignRequest, user: CurrentDbUser,
) -> PresignResponse:
    payload = make_presigned_put(
        user_id=str(user.id),
        kind=body.kind,
        content_type=body.content_type,
        expires_sec=body.expires_sec,
    )
    return PresignResponse(**payload)
