"""Media library endpoints — Phase 2.5.

Surface:

  POST /api/media/search   — provider search (Pexels + Pixabay)
  POST /api/media/save     — persist a hit to the user's library
  GET  /api/media          — list user's saved assets
  DELETE /api/media/{id}   — remove a saved asset

The search endpoint never writes to the DB — it's a pass-through to the
external providers. Save/list/delete touch ``media_assets``.
"""

from __future__ import annotations

import logging
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentDbUser
from app.db.models import MediaAsset
from app.db.session import get_db
from app.services.media import search as provider_search


logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/media", tags=["media"])


# ─── /api/media/search ──────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    kind: Literal["video", "image"] = "video"
    orientation: Literal["any", "vertical", "horizontal", "square"] = "any"
    providers: Optional[list[Literal["pexels", "pixabay"]]] = None
    page: int = Field(1, ge=1, le=50)


class SearchResponse(BaseModel):
    hits: list[dict]
    warnings: list[str]


@router.post("/search", response_model=SearchResponse)
def search_media(
    body: SearchRequest,
    _user: CurrentDbUser,
) -> SearchResponse:
    hits, warnings = provider_search(
        query=body.query,
        kind=body.kind,
        orientation=body.orientation,
        providers=body.providers,
        page=body.page,
    )
    return SearchResponse(
        hits=[h.to_dict() for h in hits],
        warnings=warnings,
    )


# ─── /api/media/save ────────────────────────────────────────────────────

class SaveRequest(BaseModel):
    provider: str = Field(..., min_length=1, max_length=32)
    provider_asset_id: str = Field(..., min_length=1, max_length=128)
    kind: Literal["video", "image"]
    url: str = Field(..., min_length=8, max_length=1000)
    thumbnail_url: Optional[str] = Field(None, max_length=1000)
    width: Optional[int] = None
    height: Optional[int] = None
    duration_sec: Optional[float] = None
    orientation: Optional[str] = Field(None, max_length=16)
    tags: list[str] = Field(default_factory=list)
    attribution: Optional[str] = Field(None, max_length=500)


class MediaAssetOut(BaseModel):
    id: uuid.UUID
    provider: str
    provider_asset_id: str
    kind: str
    url: str
    thumbnail_url: Optional[str]
    width: Optional[int]
    height: Optional[int]
    duration_sec: Optional[float]
    orientation: Optional[str]
    tags: list[str]
    attribution: Optional[str]


def _to_out(a: MediaAsset) -> MediaAssetOut:
    return MediaAssetOut(
        id=a.id,
        provider=a.provider,
        provider_asset_id=a.provider_asset_id,
        kind=a.kind,
        url=a.url,
        thumbnail_url=a.thumbnail_url,
        width=a.width,
        height=a.height,
        duration_sec=a.duration_sec,
        orientation=a.orientation,
        tags=list(a.tags or []),
        attribution=a.attribution,
    )


@router.post("/save", response_model=MediaAssetOut, status_code=201)
def save_asset(
    body: SaveRequest,
    user: CurrentDbUser,
    db: Session = Depends(get_db),
) -> MediaAssetOut:
    asset = MediaAsset(
        user_id=user.id,
        provider=body.provider,
        provider_asset_id=body.provider_asset_id,
        kind=body.kind,
        url=body.url,
        thumbnail_url=body.thumbnail_url,
        width=body.width,
        height=body.height,
        duration_sec=body.duration_sec,
        orientation=body.orientation,
        tags=body.tags,
        attribution=body.attribution,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return _to_out(asset)


# ─── /api/media (list) ──────────────────────────────────────────────────

@router.get("", response_model=list[MediaAssetOut])
def list_assets(
    user: CurrentDbUser,
    db: Session = Depends(get_db),
    kind: Optional[Literal["video", "image"]] = None,
    orientation: Optional[Literal["vertical", "horizontal", "square"]] = None,
) -> list[MediaAssetOut]:
    stmt = (
        select(MediaAsset)
        .where(MediaAsset.user_id == user.id)
        .order_by(MediaAsset.created_at.desc())
    )
    if kind is not None:
        stmt = stmt.where(MediaAsset.kind == kind)
    if orientation is not None:
        stmt = stmt.where(MediaAsset.orientation == orientation)
    return [_to_out(a) for a in db.scalars(stmt).all()]


# ─── /api/media/{id} (delete) ───────────────────────────────────────────

@router.delete("/{asset_id}", status_code=204, response_class=Response)
def delete_asset(
    asset_id: uuid.UUID,
    user: CurrentDbUser,
    db: Session = Depends(get_db),
) -> Response:
    asset = db.get(MediaAsset, asset_id)
    if asset is None or asset.user_id != user.id:
        raise HTTPException(status_code=404, detail="not found")
    db.delete(asset)
    db.commit()
    return Response(status_code=204)
