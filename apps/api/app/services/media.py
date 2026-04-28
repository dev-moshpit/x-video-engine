"""Media library — Pexels + Pixabay search + saved-asset persistence.

Phase 2.5. The api owns the search-and-save surface; the *use* of saved
assets happens later when an adapter resolves a ``*_url`` field. This
module is the only place that talks to the external providers — keeps
api keys and rate-limit handling concentrated.

Provider keys come from env vars:

  PEXELS_API_KEY   — https://www.pexels.com/api/
  PIXABAY_API_KEY  — https://pixabay.com/api/docs/

If a key is missing, the corresponding provider is silently skipped
in ``search`` (no crash). When *all* requested providers are missing
keys, ``search`` returns an empty list along with a ``warnings`` array
on the wrapping endpoint so the frontend can show a "set up keys"
prompt.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Literal, Optional

import httpx


logger = logging.getLogger(__name__)


Kind = Literal["video", "image"]
Provider = Literal["pexels", "pixabay"]
Orientation = Literal["any", "vertical", "horizontal", "square"]


@dataclass(frozen=True)
class SearchHit:
    """Provider-agnostic search result."""
    provider: str
    provider_asset_id: str
    kind: Kind
    url: str               # direct media URL (mp4 for video, jpg/png for image)
    thumbnail_url: str
    width: int
    height: int
    duration_sec: Optional[float]
    orientation: str       # "vertical" | "horizontal" | "square"
    tags: list[str]
    attribution: str       # "Photo by X via Pexels"

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "provider_asset_id": self.provider_asset_id,
            "kind": self.kind,
            "url": self.url,
            "thumbnail_url": self.thumbnail_url,
            "width": self.width,
            "height": self.height,
            "duration_sec": self.duration_sec,
            "orientation": self.orientation,
            "tags": list(self.tags),
            "attribution": self.attribution,
        }


def _orientation_from_dims(w: int, h: int) -> str:
    if h > w:
        return "vertical"
    if w > h:
        return "horizontal"
    return "square"


# ─── Pexels ─────────────────────────────────────────────────────────────

def _pexels_orientation_param(o: Orientation) -> Optional[str]:
    if o == "vertical":
        return "portrait"
    if o == "horizontal":
        return "landscape"
    if o == "square":
        return "square"
    return None


def _pexels_pick_video_file(files: list[dict]) -> Optional[dict]:
    """Pick the best mp4 from Pexels' tiered ``video_files`` list.

    Prefer 720p mp4 — small enough to download fast in dev, big enough
    to look right at 9:16. Falls back to highest available if none.
    """
    mp4s = [f for f in files if f.get("file_type") == "video/mp4"]
    if not mp4s:
        return None
    target = next(
        (f for f in mp4s if f.get("quality") == "hd" and (f.get("height") or 0) <= 1080),
        None,
    )
    return target or max(mp4s, key=lambda f: (f.get("height") or 0))


def _search_pexels(
    query: str, kind: Kind, orientation: Orientation, page: int,
) -> list[SearchHit]:
    api_key = os.environ.get("PEXELS_API_KEY")
    if not api_key:
        return []

    headers = {"Authorization": api_key}
    params: dict = {"query": query, "per_page": 20, "page": page}
    if (po := _pexels_orientation_param(orientation)):
        params["orientation"] = po

    url = (
        "https://api.pexels.com/videos/search"
        if kind == "video"
        else "https://api.pexels.com/v1/search"
    )

    try:
        resp = httpx.get(url, headers=headers, params=params, timeout=15.0)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("pexels search failed: %s", exc)
        return []

    body = resp.json()
    hits: list[SearchHit] = []

    if kind == "video":
        for v in body.get("videos", []):
            picked = _pexels_pick_video_file(v.get("video_files") or [])
            if not picked:
                continue
            w = picked.get("width") or v.get("width") or 0
            h = picked.get("height") or v.get("height") or 0
            thumb = ""
            pics = v.get("video_pictures") or []
            if pics:
                thumb = pics[0].get("picture") or ""
            user = (v.get("user") or {}).get("name") or "Pexels"
            hits.append(
                SearchHit(
                    provider="pexels",
                    provider_asset_id=str(v.get("id")),
                    kind="video",
                    url=picked.get("link") or "",
                    thumbnail_url=thumb,
                    width=int(w),
                    height=int(h),
                    duration_sec=float(v.get("duration") or 0),
                    orientation=_orientation_from_dims(int(w), int(h)),
                    tags=[],
                    attribution=f"Video by {user} via Pexels",
                )
            )
    else:
        for p in body.get("photos", []):
            src = p.get("src") or {}
            w = p.get("width") or 0
            h = p.get("height") or 0
            user = (p.get("photographer") or "Pexels")
            hits.append(
                SearchHit(
                    provider="pexels",
                    provider_asset_id=str(p.get("id")),
                    kind="image",
                    url=src.get("large2x") or src.get("large") or src.get("original") or "",
                    thumbnail_url=src.get("medium") or "",
                    width=int(w),
                    height=int(h),
                    duration_sec=None,
                    orientation=_orientation_from_dims(int(w), int(h)),
                    tags=[],
                    attribution=f"Photo by {user} via Pexels",
                )
            )

    return hits


# ─── Pixabay ────────────────────────────────────────────────────────────

def _pixabay_orientation_param(o: Orientation) -> Optional[str]:
    if o == "vertical":
        return "vertical"
    if o == "horizontal":
        return "horizontal"
    return None


def _search_pixabay(
    query: str, kind: Kind, orientation: Orientation, page: int,
) -> list[SearchHit]:
    api_key = os.environ.get("PIXABAY_API_KEY")
    if not api_key:
        return []

    params: dict = {
        "key": api_key,
        "q": query,
        "page": page,
        "per_page": 20,
    }
    if (po := _pixabay_orientation_param(orientation)):
        params["orientation"] = po

    url = (
        "https://pixabay.com/api/videos/"
        if kind == "video"
        else "https://pixabay.com/api/"
    )

    try:
        resp = httpx.get(url, params=params, timeout=15.0)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("pixabay search failed: %s", exc)
        return []

    body = resp.json()
    hits: list[SearchHit] = []

    if kind == "video":
        for v in body.get("hits", []):
            videos = v.get("videos") or {}
            # Pixabay tiers: large > medium > small > tiny. Pick "medium"
            # for the same speed/quality balance as Pexels' 720p pick.
            tier = (
                videos.get("medium")
                or videos.get("large")
                or videos.get("small")
                or videos.get("tiny")
            )
            if not tier or not tier.get("url"):
                continue
            w = tier.get("width") or 0
            h = tier.get("height") or 0
            tags = [t.strip() for t in (v.get("tags") or "").split(",") if t.strip()]
            user = v.get("user") or "Pixabay"
            hits.append(
                SearchHit(
                    provider="pixabay",
                    provider_asset_id=str(v.get("id")),
                    kind="video",
                    url=tier.get("url") or "",
                    thumbnail_url=v.get("picture_id")
                    and f"https://i.vimeocdn.com/video/{v['picture_id']}_640x360.jpg"
                    or "",
                    width=int(w),
                    height=int(h),
                    duration_sec=float(v.get("duration") or 0),
                    orientation=_orientation_from_dims(int(w), int(h)),
                    tags=tags,
                    attribution=f"Video by {user} via Pixabay",
                )
            )
    else:
        for p in body.get("hits", []):
            w = p.get("imageWidth") or 0
            h = p.get("imageHeight") or 0
            tags = [t.strip() for t in (p.get("tags") or "").split(",") if t.strip()]
            user = p.get("user") or "Pixabay"
            hits.append(
                SearchHit(
                    provider="pixabay",
                    provider_asset_id=str(p.get("id")),
                    kind="image",
                    url=p.get("largeImageURL") or p.get("webformatURL") or "",
                    thumbnail_url=p.get("previewURL") or "",
                    width=int(w),
                    height=int(h),
                    duration_sec=None,
                    orientation=_orientation_from_dims(int(w), int(h)),
                    tags=tags,
                    attribution=f"Photo by {user} via Pixabay",
                )
            )

    return hits


# ─── Public surface ─────────────────────────────────────────────────────

def search(
    *,
    query: str,
    kind: Kind = "video",
    orientation: Orientation = "any",
    providers: list[Provider] | None = None,
    page: int = 1,
) -> tuple[list[SearchHit], list[str]]:
    """Search across the requested providers.

    Returns ``(hits, warnings)``. ``warnings`` enumerates providers
    that were requested but skipped (missing api key) so the frontend
    can prompt the operator to set them up.
    """
    if providers is None:
        providers = ["pexels", "pixabay"]

    hits: list[SearchHit] = []
    warnings: list[str] = []

    for prov in providers:
        if prov == "pexels":
            if not os.environ.get("PEXELS_API_KEY"):
                warnings.append("PEXELS_API_KEY not set — Pexels skipped")
                continue
            hits.extend(_search_pexels(query, kind, orientation, page))
        elif prov == "pixabay":
            if not os.environ.get("PIXABAY_API_KEY"):
                warnings.append("PIXABAY_API_KEY not set — Pixabay skipped")
                continue
            hits.extend(_search_pixabay(query, kind, orientation, page))
        else:
            warnings.append(f"unknown provider '{prov}'")

    return hits, warnings
