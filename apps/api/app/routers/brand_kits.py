"""Brand-kit endpoints — Phase 6.

  GET  /api/me/brand-kit       — fetch (returns nulls when unset)
  PUT  /api/me/brand-kit       — upsert (any field can be null)
  DELETE /api/me/brand-kit     — clear

The render endpoint copies the kit values into the queued
``RenderJobRequest.brand_kit`` so the worker can apply them without
a separate DB read. Color-aware templates pick up brand_color +
accent_color when present; the rest of the templates ignore the
field — partial branding is fine.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth.deps import CurrentDbUser
from app.db.models import BrandKit
from app.db.session import DbSession


router = APIRouter(prefix="/api/me", tags=["brand-kit"])


_HEX = r"^#[0-9a-fA-F]{6}$"


class BrandKitInput(BaseModel):
    brand_color: Optional[str] = Field(None, pattern=_HEX)
    accent_color: Optional[str] = Field(None, pattern=_HEX)
    text_color: Optional[str] = Field(None, pattern=_HEX)
    logo_url: Optional[str] = Field(None, max_length=1000)
    brand_name: Optional[str] = Field(None, max_length=120)


class BrandKitOut(BrandKitInput):
    pass


def _to_out(kit: Optional[BrandKit]) -> BrandKitOut:
    if kit is None:
        return BrandKitOut()
    return BrandKitOut(
        brand_color=kit.brand_color,
        accent_color=kit.accent_color,
        text_color=kit.text_color,
        logo_url=kit.logo_url,
        brand_name=kit.brand_name,
    )


def get_user_brand_kit(db, user_id) -> Optional[BrandKit]:
    """Helper for other modules (renders router) — fetch the kit row."""
    return db.execute(
        select(BrandKit).where(BrandKit.user_id == user_id)
    ).scalars().first()


@router.get("/brand-kit", response_model=BrandKitOut)
def get_brand_kit(
    user: CurrentDbUser, db: DbSession,
) -> BrandKitOut:
    return _to_out(get_user_brand_kit(db, user.id))


@router.put("/brand-kit", response_model=BrandKitOut)
def upsert_brand_kit(
    body: BrandKitInput,
    user: CurrentDbUser,
    db: DbSession,
) -> BrandKitOut:
    existing = get_user_brand_kit(db, user.id)
    if existing is None:
        existing = BrandKit(
            user_id=user.id,
            brand_color=body.brand_color,
            accent_color=body.accent_color,
            text_color=body.text_color,
            logo_url=body.logo_url,
            brand_name=body.brand_name,
        )
        db.add(existing)
    else:
        existing.brand_color = body.brand_color
        existing.accent_color = body.accent_color
        existing.text_color = body.text_color
        existing.logo_url = body.logo_url
        existing.brand_name = body.brand_name
    db.commit()
    db.refresh(existing)
    return _to_out(existing)


@router.delete("/brand-kit", status_code=204, response_class=Response)
def delete_brand_kit(
    user: CurrentDbUser, db: DbSession,
) -> Response:
    existing = get_user_brand_kit(db, user.id)
    if existing is None:
        raise HTTPException(404, "no brand kit set")
    db.delete(existing)
    db.commit()
    return Response(status_code=204)
